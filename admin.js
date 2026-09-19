document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('startButton');
    const endButton = document.getElementById('endButton');
    const status = document.getElementById('status');

    const socketUrl = `ws://${location.hostname}:8766`; // ページを開いたホスト(=サーバーPC)に自動接続
    let socket;

    function setButtonsEnabled(enabled) {
        startButton.disabled = !enabled;
        endButton.disabled = !enabled;
    }

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
            setButtonsEnabled(true);
        };

        socket.onmessage = (event) => {
            console.log('サーバーからのメッセージ:', event.data);
            let data = null;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return;
            }

            if (data.type === 'ack' && data.action === 'start') {
                if (data.ok) {
                    status.textContent = `開始しました: ${data.name}さん「${data.question}」`;
                    status.style.color = 'green';
                } else {
                    status.textContent = data.message || '質問がありません。';
                    status.style.color = 'orange';
                }
            } else if (data.type === 'ack' && data.action === 'end') {
                status.textContent = '表示をクリアしました。';
                status.style.color = 'green';
            }
        };

        socket.onclose = () => {
            console.log('WebSocketサーバーから切断されました。');
            status.textContent = 'サーバーから切断されました。再接続試行中...';
            status.style.color = 'orange';
            setButtonsEnabled(false);
            setTimeout(connect, 5000);
        };

        socket.onerror = (error) => {
            console.error('WebSocketエラー:', error);
            status.textContent = '接続エラーが発生しました。';
            status.style.color = 'red';
            setButtonsEnabled(false);
            socket.close();
        };
    }

    startButton.addEventListener('click', () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'start' }));
        }
    });

    endButton.addEventListener('click', () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'end' }));
        }
    });

    setButtonsEnabled(false);
    connect();
});
