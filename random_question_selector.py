
import pygame
import random
import os
import sys
import json
import logging
from websockets.sync.client import connect as ws_connect

# --- 設定 ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)
FONT_SIZE = 32
FONT_NAME_JP = 'meiryo'  # Windowsの日本語フォント
FONT_NAME_FALLBACK = None # デフォルトフォント
QUESTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Q")
SERVER_URL = "ws://localhost:8765"  # server.pyと同じマシンで動かす想定

# --- データ ---
names = ["加藤", "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林"]

# --- 関数 ---
def get_random_question_and_delete():
    """
    Qディレクトリからランダムに質問ファイルを1つ選び、
    内容を読み込んでからファイルを削除する。
    """
    question_files = [f for f in os.listdir(QUESTION_DIR) if f.endswith('.txt')]
    if not question_files:
        return "質問がありません！", None

    chosen_file = random.choice(question_files)
    file_path = os.path.join(QUESTION_DIR, chosen_file)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            question_text = f.read().strip()
        os.remove(file_path)
        return question_text, file_path
    except Exception as e:
        return f"エラーが発生しました: {e}", None

def get_random_name():
    """namesリストからランダムに名前を1つ選ぶ"""
    return random.choice(names)

def broadcast_result(name, question):
    """選ばれた名前・質問をサーバー経由でスマホ側クライアントに配信する"""
    payload = json.dumps({"type": "result", "name": name, "question": question}, ensure_ascii=False)
    try:
        with ws_connect(SERVER_URL) as ws:
            ws.send(payload)
    except Exception as e:
        logging.warning(f"結果の配信に失敗しました(サーバー未起動の可能性): {e}")

def draw_text(surface, text, font, color, rect, aa=True):
    """
    指定された矩形内にテキストを折り返して描画する
    """
    y = rect.top
    line_spacing = -2

    # テキストを行に分割
    lines = text.splitlines()
    for text_line in lines:
        while text_line:
            i = 1
            # 矩形の幅に収まる最大の文字数を見つける
            while font.size(text_line[:i])[0] < rect.width and i < len(text_line):
                i += 1
            
            # 収まらない場合は、単語の区切りで分割を試みる
            if i < len(text_line):
                i = text_line.rfind(" ", 0, i) + 1
                if i == 0: # 単語が長すぎる場合
                    i = len(text_line)

            image = font.render(text_line[:i], aa, color)
            surface.blit(image, (rect.left, y))
            y += font.size(text_line[:i])[1] + line_spacing
            text_line = text_line[i:]

# --- メイン処理 ---
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("ランダム質問選択")
    clock = pygame.time.Clock()

    # 日本語フォントの読み込みを試みる
    try:
        font = pygame.font.SysFont(FONT_NAME_JP, FONT_SIZE)
    except:
        font = pygame.font.Font(FONT_NAME_FALLBACK, FONT_SIZE)
        print(f"警告: '{FONT_NAME_JP}'フォントが見つかりません。デフォルトフォントを使用します。")


    # 初期データ取得
    name = get_random_name()
    question, picked_path = get_random_question_and_delete()
    if picked_path:
        broadcast_result(name, question)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    # Enterキーで次の質問へ
                    name = get_random_name()
                    question, picked_path = get_random_question_and_delete()
                    if picked_path:
                        broadcast_result(name, question)

        # 描画
        screen.fill(BACKGROUND_COLOR)
        
        if question:
            display_text = f"{name}さん：「{question}」"
            text_rect = pygame.Rect(50, 50, SCREEN_WIDTH - 100, SCREEN_HEIGHT - 100)
            draw_text(screen, display_text, font, TEXT_COLOR, text_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()
