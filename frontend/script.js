const micBtn = document.getElementById('mic-toggle');
const statusText = document.getElementById('status-text');
const subStatus = document.getElementById('sub-status');
const timeDisplay = document.getElementById('current-time');
const dateDisplay = document.getElementById('current-date');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const newChatBtn = document.getElementById('new-chat-btn');
const chatHistoryContainer = document.getElementById('chat-history');
const userTextWindow = document.getElementById('user-text-window');
const userTextDisplay = document.getElementById('user-text-display');

let isListening = false;

function updateTime() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    if (timeDisplay) timeDisplay.textContent = `${hours}:${minutes}`;

    const options = { weekday: 'long', day: 'numeric', month: 'long' };
    const dateStr = now.toLocaleDateString('ru-RU', options);
    if (dateDisplay) dateDisplay.textContent = dateStr;
}
setInterval(updateTime, 1000);
updateTime();

sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
});

// ===== Состояние чатов (в памяти, при запуске — чисто) =====
let currentSessionId = null;
let currentMessages = [];
let pastSessions = [];

// Загрузить историю прошлых чатов из БД при старте
async function loadPastSessions() {
    if (!(window.pywebview && window.pywebview.api)) return;
    try {
        pastSessions = await window.pywebview.api.get_chat_history();
    } catch (e) {
        console.error("Ошибка загрузки истории:", e);
        pastSessions = [];
    }
    renderSidebar();
}

// ===== Рендер боковой панели =====
function renderSidebar() {
    chatHistoryContainer.innerHTML = '';

    // Текущий чат (если есть сообщения)
    if (currentMessages.length > 0) {
        const currentItem = document.createElement('div');
        currentItem.className = 'chat-session active';

        const title = document.createElement('div');
        title.className = 'chat-title';
        const firstUserMsg = currentMessages.find(m => m.sender === 'user');
        title.textContent = firstUserMsg ? firstUserMsg.text : 'Текущий чат';

        const msgsBlock = document.createElement('div');
        msgsBlock.className = 'chat-messages';

        currentMessages.forEach(m => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `msg ${m.sender}`;
            msgDiv.textContent = m.text;
            msgsBlock.appendChild(msgDiv);
        });

        currentItem.appendChild(title);
        currentItem.appendChild(msgsBlock);
        chatHistoryContainer.appendChild(currentItem);
    }

    // Прошлые чаты из БД
    pastSessions.forEach(session => {
        // Не показывать текущую сессию дважды
        if (session.id === currentSessionId) return;

        const chatItem = document.createElement('div');
        chatItem.className = 'chat-session';

        const titleRow = document.createElement('div');
        titleRow.className = 'chat-title-row';

        const title = document.createElement('div');
        title.className = 'chat-title';
        title.textContent = session.title || 'Чат';
        title.onclick = async () => {
            await showSessionMessages(session.id, chatItem);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'chat-delete-btn';
        deleteBtn.textContent = '✕';
        deleteBtn.title = 'Удалить чат';
        deleteBtn.onclick = async (e) => {
            e.stopPropagation();
            if (window.pywebview && window.pywebview.api) {
                await window.pywebview.api.delete_chat(session.id);
                await loadPastSessions();
            }
        };

        const meta = document.createElement('div');
        meta.className = 'chat-meta';
        meta.textContent = `${session.message_count} сообщ.`;

        titleRow.appendChild(title);
        titleRow.appendChild(deleteBtn);

        chatItem.appendChild(titleRow);
        chatItem.appendChild(meta);
        chatHistoryContainer.appendChild(chatItem);
    });
}

// Показать сообщения прошлого чата
async function showSessionMessages(sessionId, chatItem) {
    if (!(window.pywebview && window.pywebview.api)) return;

    // Если уже раскрыт — свернуть
    const existing = chatItem.querySelector('.chat-messages');
    if (existing) {
        existing.remove();
        return;
    }

    try {
        const messages = await window.pywebview.api.get_chat_messages(sessionId);
        const msgsBlock = document.createElement('div');
        msgsBlock.className = 'chat-messages';

        messages.forEach(m => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `msg ${m.sender}`;
            msgDiv.textContent = m.text;
            msgsBlock.appendChild(msgDiv);
        });

        chatItem.appendChild(msgsBlock);
    } catch (e) {
        console.error("Ошибка загрузки сообщений:", e);
    }
}

// ===== Новый чат =====
newChatBtn.addEventListener('click', async () => {
    // Начать новый чат
    currentSessionId = null;
    currentMessages = [];
    userTextWindow.style.opacity = '0';
    await loadPastSessions();
    renderSidebar();
});

// ===== Добавление сообщения =====
function addMessage(text, sender) {
    currentMessages.push({ text, sender });
    renderSidebar();

    if (sender === 'user') {
        userTextDisplay.textContent = `Вы сказали: "${text}"`;
        userTextWindow.style.opacity = '1';
    }
}

// Создать сессию в БД при первом сообщении
async function ensureSession() {
    if (currentSessionId) return;
    if (window.pywebview && window.pywebview.api) {
        try {
            const result = await window.pywebview.api.create_chat_session("Новый чат");
            currentSessionId = result.session_id;
        } catch (e) {
            console.error("Ошибка создания сессии:", e);
        }
    }
}

// ===== Инициализация =====
window.addEventListener('pywebviewready', async () => {
    await loadPastSessions();
    // Создаём сессию для нового чата сразу
    await ensureSession();
    setTimeout(() => { backgroundListen(); }, 500);
});

// ===== Фоновое прослушивание =====
let isBackgroundListening = false;

async function backgroundListen() {
    if (isListening) return;
    isBackgroundListening = true;

    if (!(window.pywebview && window.pywebview.api)) {
        isBackgroundListening = false;
        return;
    }

    try {
        const result = await window.pywebview.api.listen_voice();
        if (isListening) { isBackgroundListening = false; return; }

        if (result.status === "wake") {
            isListening = true;
            isBackgroundListening = false;
            const voiceHub = document.querySelector('.voice-hub');
            if (voiceHub) voiceHub.classList.add('active');
            statusText.textContent = "Слушаю...";
            subStatus.textContent = "Говорите команду";
            userTextDisplay.textContent = "Я вас слушаю...";
            userTextWindow.style.opacity = '1';
            addMessage(result.text, 'bot');
            if (result.audio_base64) {
                const audio = new Audio("data:audio/mp3;base64," + result.audio_base64);
                audio.play();
            } else {
                window.pywebview.api.speak(result.text);
            }
            setTimeout(() => { startListening(); }, 300);
        } else if (result.status === "success" && result.text) {
            isListening = true;
            isBackgroundListening = false;
            const voiceHub = document.querySelector('.voice-hub');
            if (voiceHub) voiceHub.classList.add('active');
            processCommand(result.text);
        } else {
            isBackgroundListening = false;
            if (!isListening) {
                setTimeout(() => { backgroundListen(); }, 300);
            }
        }
    } catch (e) {
        console.error("Background listen error:", e);
        isBackgroundListening = false;
        if (!isListening) {
            setTimeout(() => { backgroundListen(); }, 1000);
        }
    }
}

micBtn.addEventListener('click', async () => {
    if (isListening) {
        stopListening();
        setTimeout(() => { backgroundListen(); }, 500);
    } else {
        if (isBackgroundListening && window.pywebview && window.pywebview.api) {
            window.pywebview.api.stop_listening();
        }
        isListening = true;
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_awake();
        }
        await startListening();
    }
});

async function startListening() {
    const voiceHub = document.querySelector('.voice-hub');
    if (voiceHub) voiceHub.classList.add('active');

    statusText.textContent = "Слушаю...";
    subStatus.textContent = "Говорите прямо сейчас";
    userTextDisplay.textContent = "Слушаю...";
    userTextWindow.style.opacity = '1';

    if (window.pywebview && window.pywebview.api) {
        try {
            const result = await window.pywebview.api.listen_voice();
            if (!isListening) return;

            if (result.status === "success" && result.text) {
                processCommand(result.text);
            } else if (result.status === "wake") {
                addMessage(result.text, 'bot');
                window.pywebview.api.speak(result.text);
                if (isListening) {
                    setTimeout(() => { startListening(); }, 300);
                }
            } else if (result.status === "ignore") {
                if (isListening) {
                    setTimeout(() => { startListening(); }, 300);
                }
            } else if (result.status === "error") {
                addMessage(`Ошибка: ${result.message}`, 'bot');
                stopListening();
                setTimeout(() => { backgroundListen(); }, 500);
            }
        } catch (e) {
            console.error("Voice API Error:", e);
            stopListening();
            setTimeout(() => { backgroundListen(); }, 500);
        }
    } else {
        setTimeout(() => {
            if (isListening) processCommand("Открой браузер");
        }, 3000);
    }
}

function stopListening() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.stop_listening();
    }
    const voiceHub = document.querySelector('.voice-hub');
    if (voiceHub) voiceHub.classList.remove('active');

    statusText.textContent = "Система готова";
    subStatus.textContent = "Нажмите 🎤 для новой записи";
    isListening = false;
}

async function processCommand(command) {
    await ensureSession();
    addMessage(command, 'user');

    statusText.textContent = "Обработка...";
    subStatus.textContent = "Анализирую запрос";

    if (window.pywebview && window.pywebview.api) {
        try {
            const result = await window.pywebview.api.handle_command(command);
            setTimeout(() => {
                addMessage(result.response, 'bot');
                if (result.audio_base64) {
                    const audio = new Audio("data:audio/mp3;base64," + result.audio_base64);
                    audio.play();
                }
                stopListening();
                setTimeout(() => { backgroundListen(); }, 500);
            }, 800);
        } catch (e) {
            console.error("NLP Error:", e);
            addMessage("Произошла ошибка связи с ядром.", 'bot');
            stopListening();
            setTimeout(() => { backgroundListen(); }, 500);
        }
    } else {
        setTimeout(() => {
            addMessage("Команда принята (Служба NLP отключена)", 'bot');
            stopListening();
        }, 800);
    }
}
