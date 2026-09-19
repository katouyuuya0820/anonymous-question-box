
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

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_DIR = os.path.join(BASE_DIR, "Q")  # 質問を保存するフォルダ名
GENERAL_PORT = 8765  # 一般ユーザー用（質問投稿・結果表示）
ADMIN_PORT = 8766    # 管理者用（質問開始・終了）
STATIC_PORT = 8000   # HTML/JS/CSSを配信するHTTPサーバー用
PASS = "changeme"    # 管理者ページのパスワード（必ず変更してください）

# 表示に使う名前リスト（自由に編集してください）
names = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤"]

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 現在接続中の一般ユーザークライアント一覧（結果のブロードキャスト先）
general_clients = set()


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


def start_static_server():
    """index.html/admin.html等の静的ファイルをHTTPで配信する（別スレッドで実行）"""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(BASE_DIR, "static"))
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


async def general_handler(websocket):
    """一般ユーザー（質問投稿・結果表示）用ハンドラ"""
    logging.info(f"[一般] クライアントが接続しました: {websocket.remote_address}")
    general_clients.add(websocket)
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
    logging.info(f"[管理者] クライアントが接続しました: {websocket.remote_address}")
    authenticated = False
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
                await broadcast_to_general({"type": "result", "name": name, "question": question})
                await websocket.send(json.dumps(
                    {"type": "ack", "action": "start", "ok": True, "name": name, "question": question},
                    ensure_ascii=False))
                logging.info(f"質問を開始しました: {name}さん「{question}」")

            elif action == "end":
                await broadcast_to_general({"type": "clear"})
                await websocket.send(json.dumps(
                    {"type": "ack", "action": "end", "ok": True}, ensure_ascii=False))
                logging.info("表示をクリアしました。")

    except websockets.exceptions.ConnectionClosed as e:
        logging.info(f"[管理者] クライアントとの接続が切れました: {e.code} {e.reason}")
    except Exception as e:
        logging.error(f"エラーが発生しました: {e}")
    finally:
        logging.info(f"[管理者] クライアントとの接続を終了します: {websocket.remote_address}")


async def main():
    """静的ファイル配信・一般ユーザー用・管理者用のサーバーを起動するメイン関数。"""
    ip = get_local_ip()
    threading.Thread(target=start_static_server, daemon=True).start()

    async with websockets.serve(general_handler, "0.0.0.0", GENERAL_PORT), \
               websockets.serve(admin_handler, "0.0.0.0", ADMIN_PORT):
        logging.info("サーバーを起動しました。")
        logging.info(f"一般ユーザー用ページ（スマホでこれを開く）: http://{ip}:{STATIC_PORT}/index.html")
        logging.info(f"管理者用ページ（スマホでこれを開く）    : http://{ip}:{STATIC_PORT}/admin.html")
        await asyncio.Future()  # サーバーを永続的に実行


if __name__ == "__main__":
    if not os.path.exists(QUESTIONS_DIR):
        os.makedirs(QUESTIONS_DIR)
        logging.info(f"'{QUESTIONS_DIR}' フォルダを作成しました。")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("サーバーをシャットダウンします。")
