document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('questionForm');
    const questionText = document.getElementById('questionText');
    const status = document.getElementById('status');
    const submitButton = form.querySelector('button');
    const resultArea = document.getElementById('resultArea');
    const resultName = document.getElementById('resultName');
    const resultQuestion = document.getElementById('resultQuestion');

    const socketUrl = `ws://${location.hostname}:8765`; // ページを開いたホスト(=サーバーPC)に自動接続
    let socket;

    function connect() {
        try {
            socket = new WebSocket(socketUrl);
        } catch (e) {
            console.error("WebSocketの作成に失敗しました。", e);
            status.textContent = "サーバー接続に失敗しました。";
            status.style.color = 'red';
            return;
        }

        socket.onopen = () => {
            console.log('WebSocketサーバーに接続しました。');
            status.textContent = 'サーバーに接続しました。';
            status.style.color = 'green';
            submitButton.disabled = false;
        };

        socket.onmessage = (event) => {
            console.log('サーバーからのメッセージ:', event.data);

            // サーバーから配信される結果通知(JSON)かどうかを判定
            let data = null;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                // JSONでなければ通常の確認メッセージとして扱う
            }

            if (data && data.type === 'result') {
                resultName.textContent = data.name;
                resultQuestion.textContent = data.question;
                resultArea.hidden = false;
                return;
            }

            if (data && data.type === 'clear') {
                resultArea.hidden = true;
                resultName.textContent = '';
                resultQuestion.textContent = '';
                return;
            }

            status.textContent = event.data; // サーバーからの確認メッセージを表示
            setTimeout(() => {
                status.textContent = 'サーバーに接続しました。'; // メッセージを元に戻す
            }, 3000);
        };

        socket.onclose = () => {
            console.log('WebSocketサーバーから切断されました。');
            status.textContent = 'サーバーから切断されました。再接続試行中...';
            status.style.color = 'orange';
            submitButton.disabled = true;
            // 5秒後に再接続を試みる
            setTimeout(connect, 5000);
        };

        socket.onerror = (error) => {
            console.error('WebSocketエラー:', error);
            status.textContent = '接続エラーが発生しました。';
            status.style.color = 'red';
            submitButton.disabled = true;
            socket.close(); // エラー発生時はクリーンアップ
        };
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        const question = questionText.value.trim();
        if (question && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(question);
            console.log(`質問を送信しました: ${question}`);
            questionText.value = ''; // テキストエリアをクリア
            status.textContent = '質問を送信しました。';
        } else {
            status.textContent = '接続が確立されていないか、質問が空です。';
            status.style.color = 'red';
        }
    });

    // 初期接続
    submitButton.disabled = true;
    connect();
});
