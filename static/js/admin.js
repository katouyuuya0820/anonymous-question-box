document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const passwordInput = document.getElementById('passwordInput');
    const controls = document.getElementById('controls');
    const startButton = document.getElementById('startButton');
    const endButton = document.getElementById('endButton');
    const status = document.getElementById('status');

    const socketUrl = `ws://${location.hostname}:8766`; // ページを開いたホスト(=サーバーPC)に自動接続
    let socket;
    let authenticated = false;

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
            status.textContent = 'サーバーに接続しました。パスワードを入力してください。';
            status.style.color = 'green';
        };

        socket.onmessage = (event) => {
            console.log('サーバーからのメッセージ:', event.data);
            let data = null;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return;
            }

            if (data.type === 'ack' && data.action === 'auth') {
                authenticated = data.ok;
                if (authenticated) {
                    loginForm.hidden = true;
                    controls.hidden = false;
                    setButtonsEnabled(true);
                    status.textContent = 'ログインしました。';
                    status.style.color = 'green';
                } else {
                    status.textContent = 'パスワードが違います。';
                    status.style.color = 'red';
                }
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
            authenticated = false;
            loginForm.hidden = false;
            controls.hidden = true;
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

    loginForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const password = passwordInput.value;
        passwordInput.value = '';
        if (socket && socket.readyState === WebSocket.OPEN && password) {
            socket.send(JSON.stringify({ type: 'auth', password }));
        }
    });

    startButton.addEventListener('click', () => {
        if (socket && socket.readyState === WebSocket.OPEN && authenticated) {
            socket.send(JSON.stringify({ type: 'start' }));
        }
    });

    endButton.addEventListener('click', () => {
        if (socket && socket.readyState === WebSocket.OPEN && authenticated) {
            socket.send(JSON.stringify({ type: 'end' }));
        }
    });

    setButtonsEnabled(false);
    connect();
});
