
import asyncio
import websockets
import logging
import os
import json
import random
import socket
import threading
import functools
import http.server
from datetime import datetime

# --- adminページのパスワード ---
PASS = "" 

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_DIR = os.path.join(BASE_DIR, "Q")  # 質問を保存するフォルダ名
GENERAL_PORT = 8765  # 一般ユーザー用（質問投稿・結果表示）
ADMIN_PORT = 8766    # 管理者用（質問開始・終了）
STATIC_PORT = 8000   # HTML/JS/CSSを配信するHTTPサーバー用

# 表示に使う名前リスト（自由に編集してください）
names = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤"]

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 現在接続中の一般ユーザークライアント一覧（結果のブロードキャスト先）
general_clients = set()

# 現在接続中の管理者クライアント一覧（名前リスト変更の同期先）
admin_clients = set()

# 現在表示中の質問（{"name":..., "question":...}）。未表示のときはNone。
# 途中参加・再接続した一般ユーザーにも現在の質問を送るために保持する。
current_result = None

# サーバー起動時に確定するこのPCのLAN IP（main()で設定、admin_handlerの認証スキップ判定に使う）
SERVER_IP = None


def get_local_ip() -> str:
    """LAN内でのこのPCのIPアドレスを取得する（取得できない場合はlocalhost）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """静的ファイルをブラウザにキャッシュさせないHTTPハンドラ（更新が即反映されるように）"""
    def send_head(self):
        # 条件付きリクエストヘッダを無視して常に最新を返す（304 Not Modifiedを防ぐ）
        del self.headers["If-Modified-Since"]
        del self.headers["If-None-Match"]
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def start_static_server():
    """index.html/admin.html等の静的ファイルをHTTPで配信する（別スレッドで実行）"""
    handler = functools.partial(NoCacheHandler, directory=os.path.join(BASE_DIR, "static"))
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", STATIC_PORT), handler)
    httpd.serve_forever()


def save_question(message: str):
    """受信した質問をファイルに保存する"""
    try:
        os.makedirs(QUESTIONS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = os.path.join(QUESTIONS_DIR, f"question_{timestamp}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(message)
        logging.info(f"質問を保存しました: {file_path}")
    except Exception as e:
        logging.error(f"ファイルの保存中にエラーが発生しました: {e}")


def pick_random_question():
    """Qディレクトリからランダムに質問ファイルを1つ選び、内容を読み込んでから削除する"""
    os.makedirs(QUESTIONS_DIR, exist_ok=True)
    question_files = [f for f in os.listdir(QUESTIONS_DIR) if f.endswith('.txt')]
    if not question_files:
        return None

    chosen_file = random.choice(question_files)
    file_path = os.path.join(QUESTIONS_DIR, chosen_file)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            question_text = f.read().strip()
        os.remove(file_path)
        return question_text
    except Exception as e:
        logging.error(f"質問ファイルの読み込み中にエラーが発生しました: {e}")
        return None


async def broadcast_to_general(data: dict):
    """一般ユーザークライアント全員にメッセージを配信する"""
    payload = json.dumps(data, ensure_ascii=False)
    targets = list(general_clients)
    for client in targets:
        try:
            await client.send(payload)
        except Exception as e:
            logging.error(f"配信中にエラーが発生しました: {e}")
    logging.info(f"{len(targets)}件のクライアントに配信しました: {data}")


async def broadcast_names_to_admins():
    """認証済みの管理者クライアント全員に最新の名前リストを配信する"""
    payload = json.dumps({"type": "names", "names": names}, ensure_ascii=False)
    for client in list(admin_clients):
        try:
            await client.send(payload)
        except Exception as e:
            logging.error(f"名前リストの配信中にエラーが発生しました: {e}")


async def send_admin_init(websocket):
    """認証直後の管理者に、名前リストと参加者用URL（QR表示に使う）を送る"""
    await websocket.send(json.dumps({"type": "names", "names": names}, ensure_ascii=False))
    await websocket.send(json.dumps(
        {"type": "server_info", "url": f"http://{SERVER_IP}:{STATIC_PORT}/index.html"},
        ensure_ascii=False))


async def general_handler(websocket):
    """一般ユーザー（質問投稿・結果表示）用ハンドラ"""
    logging.info(f"[一般] クライアントが接続しました: {websocket.remote_address}")
    general_clients.add(websocket)
    # 途中参加・再接続時に、現在表示中の質問があれば送る
    if current_result is not None:
        await websocket.send(json.dumps(
            {"type": "result", "name": current_result["name"], "question": current_result["question"]},
            ensure_ascii=False))
    try:
        async for message in websocket:
            logging.info(f"質問を受信しました: {message}")
            save_question(message)
            await websocket.send("質問を受け付けました。")
    except websockets.exceptions.ConnectionClosed as e:
        logging.info(f"[一般] クライアントとの接続が切れました: {e.code} {e.reason}")
    except Exception as e:
        logging.error(f"エラーが発生しました: {e}")
    finally:
        general_clients.discard(websocket)
        logging.info(f"[一般] クライアントとの接続を終了します: {websocket.remote_address}")


async def admin_handler(websocket):
    """管理者（質問開始・終了）用ハンドラ"""
    global current_result
    logging.info(f"[管理者] クライアントが接続しました: {websocket.remote_address}")
    client_ip = websocket.remote_address[0] if websocket.remote_address else None
    # サーバー自身からのアクセス、またはパスワード未設定の場合は認証をスキップする
    authenticated = (not PASS) or (client_ip in ("127.0.0.1", "::1", SERVER_IP))
    await websocket.send(json.dumps(
        {"type": "auth_status", "required": not authenticated}, ensure_ascii=False))
    if authenticated:
        logging.info(f"[管理者] 認証をスキップしました（{client_ip}）: {websocket.remote_address}")
        admin_clients.add(websocket)
        await send_admin_init(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                continue

            action = data.get("type") if isinstance(data, dict) else None

            if action == "auth":
                authenticated = data.get("password") == PASS
                await websocket.send(json.dumps(
                    {"type": "ack", "action": "auth", "ok": authenticated}, ensure_ascii=False))
                if authenticated:
                    logging.info(f"[管理者] 認証に成功しました: {websocket.remote_address}")
                    admin_clients.add(websocket)
                    await send_admin_init(websocket)
                else:
                    logging.info(f"[管理者] 認証に失敗しました: {websocket.remote_address}")
                continue

            if not authenticated:
                await websocket.send(json.dumps(
                    {"type": "ack", "action": action, "ok": False, "message": "認証が必要です"},
                    ensure_ascii=False))
                continue

            if action == "start":
                question = pick_random_question()
                if question is None:
                    await websocket.send(json.dumps(
                        {"type": "ack", "action": "start", "ok": False, "message": "質問がありません"},
                        ensure_ascii=False))
                    continue

                name = random.choice(names)
                current_result = {"name": name, "question": question}
                await broadcast_to_general({"type": "result", "name": name, "question": question})
                await websocket.send(json.dumps(
                    {"type": "ack", "action": "start", "ok": True, "name": name, "question": question},
                    ensure_ascii=False))
                logging.info(f"質問を開始しました: {name}さん「{question}」")

            elif action == "end":
                current_result = None
                await broadcast_to_general({"type": "clear"})
                await websocket.send(json.dumps(
                    {"type": "ack", "action": "end", "ok": True}, ensure_ascii=False))
                logging.info("表示をクリアしました。")

            elif action == "get_names":
                await websocket.send(json.dumps({"type": "names", "names": names}, ensure_ascii=False))

            elif action == "add_name":
                name = (data.get("name") or "").strip()
                if not name:
                    await websocket.send(json.dumps(
                        {"type": "ack", "action": "add_name", "ok": False, "message": "名前が空です"},
                        ensure_ascii=False))
                elif name in names:
                    await websocket.send(json.dumps(
                        {"type": "ack", "action": "add_name", "ok": False, "message": "同じ名前が既にあります"},
                        ensure_ascii=False))
                else:
                    names.append(name)
                    logging.info(f"名前を追加しました: {name}")
                    await broadcast_names_to_admins()

            elif action == "remove_name":
                name = data.get("name")
                if name in names:
                    names.remove(name)
                    logging.info(f"名前を削除しました: {name}")
                    await broadcast_names_to_admins()
                else:
                    await websocket.send(json.dumps(
                        {"type": "ack", "action": "remove_name", "ok": False, "message": "その名前は存在しません"},
                        ensure_ascii=False))

    except websockets.exceptions.ConnectionClosed as e:
        logging.info(f"[管理者] クライアントとの接続が切れました: {e.code} {e.reason}")
    except Exception as e:
        logging.error(f"エラーが発生しました: {e}")
    finally:
        admin_clients.discard(websocket)
        logging.info(f"[管理者] クライアントとの接続を終了します: {websocket.remote_address}")


async def main():
    """静的ファイル配信・一般ユーザー用・管理者用のサーバーを起動するメイン関数。"""
    global SERVER_IP
    ip = get_local_ip()
    SERVER_IP = ip
    threading.Thread(target=start_static_server, daemon=True).start()

    async with websockets.serve(general_handler, "0.0.0.0", GENERAL_PORT), \
               websockets.serve(admin_handler, "0.0.0.0", ADMIN_PORT):
        logging.info("--------------------------------")
        logging.info("サーバーを起動しました。")
        logging.info(f"一般ユーザー用ページ : http://{ip}:{STATIC_PORT}/index.html")
        logging.info(f"管理者用ページ : http://{ip}:{STATIC_PORT}/admin.html")
        logging.info("--------------------------------")
        await asyncio.Future()  # サーバーを永続的に実行


if __name__ == "__main__":
    if not os.path.exists(QUESTIONS_DIR):
        os.makedirs(QUESTIONS_DIR)
        logging.info(f"'{QUESTIONS_DIR}' フォルダを作成しました。")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("サーバーをシャットダウンします。")
