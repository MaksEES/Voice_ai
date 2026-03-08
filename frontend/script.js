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

// 1. Часы и Дата
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

// 2. Панель истории чатов (открытие/закрытие)
sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
});

// 3. Логика истории чатов (по первому запросу)
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

        // Заголовок (Тема = первый запрос)
        const title = document.createElement('div');
        title.className = 'chat-title';
        title.textContent = chat.title || 'Новый чат';
        title.onclick = () => {
            currentChatIndex = index;
            renderChats(); // Пересоздать с раскрытым выбранным чатом
        };

        // Окно с сообщениями
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
        chatHistoryContainer.prepend(chatItem); // Новые чаты сверху
    });
}

// Новый чат
newChatBtn.addEventListener('click', () => {
    currentChatIndex = -1;
    // Сбрасываем субтитры
    userTextWindow.style.opacity = '0';
    renderChats();
    // Открываем панель если она закрыта
    if (!sidebar.classList.contains('open')) {
        sidebar.classList.add('open');
    }
});

// Добавление сообщения в историю
function addMessage(text, sender) {
    if (currentChatIndex === -1 || !chats[currentChatIndex]) {
        // Создаем новый чат. Если пишет пользователь, это название чата
        const title = sender === 'user' ? text : 'Голосовой чат';
        chats.push({ title: title, messages: [] });
        currentChatIndex = chats.length - 1;
    } else if (chats[currentChatIndex].messages.length === 0 && sender === 'user') {
        // Если это все еще пустой чат
        chats[currentChatIndex].title = text;
    }

    chats[currentChatIndex].messages.push({ text, sender });
    saveChats();
    renderChats();

    // Показываем текст в маленьком окне снизу
    if (sender === 'user') {
        userTextDisplay.textContent = `Вы сказали: "${text}"`;
        userTextWindow.style.opacity = '1';
    } else if (sender === 'bot') {
        // Дополнительно можно показывать ответ бота, или оставлять слова пользователя
        // userTextDisplay.textContent = `Ответ: "${text}"`;
    }
}

// Инициализация при загрузке
if (chats.length === 0) {
    // Дефолтный первый чат если все пусто
    chats.push({ title: 'Первый запуск', messages: [{ text: 'Привет! Я тестовая система. Как я могу вам помочь?', sender: 'bot' }] });
    currentChatIndex = 0;
    saveChats();
}
renderChats();

// 4. Голосовое взаимодействие
micBtn.addEventListener('click', async () => {
    isListening = !isListening;

    if (isListening) {
        await startListening();
    } else {
        stopListening();
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

            if (result.status === "success") {
                processCommand(result.text);
            } else {
                addMessage(`Ошибка: ${result.message}`, 'bot');
                stopListening();
            }
        } catch (e) {
            console.error("Voice API Error:", e);
            stopListening();
        }
    } else {
        // Мок для теста без бэкенда
        setTimeout(() => {
            if (isListening) processCommand("Открой браузер");
        }, 3000);
    }
}

function stopListening() {
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
            }, 800);
        } catch (e) {
            console.error("NLP Error:", e);
            addMessage("Произошла ошибка связи с ядром.", 'bot');
            stopListening();
        }
    } else {
        setTimeout(() => {
            addMessage("Команда принята (Служба NLP отключена)", 'bot');
            stopListening();
        }, 800);
    }
}
