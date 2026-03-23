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

let chats = JSON.parse(localStorage.getItem('chats') || '[]');
let currentChatIndex = chats.length > 0 ? chats.length - 1 : -1;

function saveChats() {
    localStorage.setItem('chats', JSON.stringify(chats));
}

function renderChats() {
    chatHistoryContainer.innerHTML = '';
    chats.forEach((chat, index) => {
        const chatItem = document.createElement('div');
        chatItem.className = 'chat-session' + (index === currentChatIndex ? ' active' : '');

        const title = document.createElement('div');
        title.className = 'chat-title';
        title.textContent = chat.title || 'Новый чат';
        title.onclick = () => {
            currentChatIndex = index;
            renderChats();
        };

        const msgsBlock = document.createElement('div');
        msgsBlock.className = 'chat-messages';
        if (index !== currentChatIndex) {
            msgsBlock.style.display = 'none';
        }

        chat.messages.forEach(m => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `msg ${m.sender}`;
            msgDiv.textContent = m.text;
            msgsBlock.appendChild(msgDiv);
        });

        chatItem.appendChild(title);
        chatItem.appendChild(msgsBlock);
        chatHistoryContainer.prepend(chatItem);
    });
}

newChatBtn.addEventListener('click', () => {
    currentChatIndex = -1;
    userTextWindow.style.opacity = '0';
    renderChats();
    if (!sidebar.classList.contains('open')) {
        sidebar.classList.add('open');
    }
});

function addMessage(text, sender) {
    if (currentChatIndex === -1 || !chats[currentChatIndex]) {
        const title = sender === 'user' ? text : 'Голосовой чат';
        chats.push({ title: title, messages: [] });
        currentChatIndex = chats.length - 1;
    } else if (chats[currentChatIndex].messages.length === 0 && sender === 'user') {
        chats[currentChatIndex].title = text;
    }

    chats[currentChatIndex].messages.push({ text, sender });
    saveChats();
    renderChats();

    if (sender === 'user') {
        userTextDisplay.textContent = `Вы сказали: "${text}"`;
        userTextWindow.style.opacity = '1';
    } else if (sender === 'bot') {
    }
}

if (chats.length === 0) {
    chats.push({ title: 'Первый запуск', messages: [{ text: 'Привет! Я тестовая система. Как я могу вам помочь?', sender: 'bot' }] });
    currentChatIndex = 0;
    saveChats();
}
renderChats();

// === Фоновое прослушивание wake word ===
let isBackgroundListening = false;

async function backgroundListen() {
    if (isListening) return; // ручной режим активен
    isBackgroundListening = true;

    if (!(window.pywebview && window.pywebview.api)) {
        isBackgroundListening = false;
        return;
    }

    try {
        const result = await window.pywebview.api.listen_voice();
        if (isListening) { isBackgroundListening = false; return; }

        if (result.status === "wake") {
            // Wake word обнаружен! Активируем UI и слушаем команду
            isListening = true;
            isBackgroundListening = false;
            const voiceHub = document.querySelector('.voice-hub');
            if (voiceHub) voiceHub.classList.add('active');
            statusText.textContent = "Слушаю...";
            subStatus.textContent = "Говорите команду";
            userTextDisplay.textContent = "Я вас слушаю...";
            userTextWindow.style.opacity = '1';
            addMessage(result.text, 'bot');
            window.pywebview.api.speak(result.text);
            setTimeout(() => { startListening(); }, 300);
        } else if (result.status === "success" && result.text) {
            // Команда с wake word в одной фразе ("Макс открой калькулятор")
            isListening = true;
            isBackgroundListening = false;
            const voiceHub = document.querySelector('.voice-hub');
            if (voiceHub) voiceHub.classList.add('active');
            processCommand(result.text);
        } else {
            // ignore — перезапускаем фоновое прослушивание
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

// Запуск фонового прослушивания при старте приложения (кнопка микрофона выключена)
window.addEventListener('pywebviewready', () => {
    setTimeout(() => { backgroundListen(); }, 500);
});

// === Кнопка микрофона (ручной режим) ===
micBtn.addEventListener('click', async () => {
    if (isListening) {
        stopListening();
        // Перезапускаем фоновое прослушивание через паузу
        setTimeout(() => { backgroundListen(); }, 500);
    } else {
        // Остановить фоновое прослушивание если оно активно
        if (isBackgroundListening && window.pywebview && window.pywebview.api) {
            window.pywebview.api.stop_listening();
        }
        isListening = true;
        // Пропускаем wake word — пользователь сам нажал кнопку
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
                // После выполнения команды — возвращаемся к фоновому прослушиванию
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
