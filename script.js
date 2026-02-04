// DOM Elements
const micBtn = document.getElementById('mic-toggle');
const statusText = document.getElementById('status-text');
const subStatus = document.getElementById('sub-status');
const chatHistory = document.getElementById('chat-history');
const timeDisplay = document.getElementById('current-time');

// Update Clock & Date
function updateTime() {
    const now = new Date();

    // Time
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    if (timeDisplay) timeDisplay.textContent = `${hours}:${minutes}`;

    // Date
    const options = { weekday: 'long', day: 'numeric', month: 'long' };
    const dateStr = now.toLocaleDateString('ru-RU', options);
    const dateDisplay = document.getElementById('current-date');
    if (dateDisplay) dateDisplay.textContent = dateStr;
}
setInterval(updateTime, 1000);
updateTime();

// Update System Stats from Python Backend
async function updateStatsFromBackend() {
    if (window.pywebview && window.pywebview.api) {
        try {
            const stats = await window.pywebview.api.get_system_stats();
            const cpuFill = document.getElementById('cpu-fill');
            const ramFill = document.getElementById('ram-fill');

            if (cpuFill) {
                cpuFill.style.width = stats.cpu + '%';
                cpuFill.parentElement.previousElementSibling.querySelector('span').textContent = Math.round(stats.cpu) + '%';
            }
            if (ramFill) {
                ramFill.style.width = stats.ram + '%';
                ramFill.parentElement.previousElementSibling.querySelector('span').textContent = Math.round(stats.ram) + '%';
            }
        } catch (e) {
            console.error("Failed to fetch stats:", e);
        }
    }
}
setInterval(updateStatsFromBackend, 3000);

// Voice Interaction Logic
let isListening = false;

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
    subStatus.textContent = "Я весь во внимании";

    // Call Python Voice API (ASR)
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
        // Fallback simulation
        setTimeout(() => {
            if (isListening) processCommand("Открой браузер");
        }, 3000);
    }
}

function stopListening() {
    const voiceHub = document.querySelector('.voice-hub');
    if (voiceHub) voiceHub.classList.remove('active');

    statusText.textContent = "Система готова";
    subStatus.textContent = "Скажите команду или нажмите кнопку";
    isListening = false;
}

async function processCommand(command) {
    addMessage(command, 'user');

    statusText.textContent = "Обработка...";
    subStatus.textContent = "Сверка с базой данных";

    if (window.pywebview && window.pywebview.api) {
        try {
            const result = await window.pywebview.api.handle_command(command);

            setTimeout(() => {
                addMessage(result.response, 'bot');
                if (result.intent === "GET_STATS") updateStatsFromBackend();
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

// Navigation Buttons Logic
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelector('.nav-btn.active').classList.remove('active');
        btn.classList.add('active');

        const page = btn.getAttribute('data-tooltip');
        addMessage(`Переход в раздел: ${page}`, 'bot');
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.speak(`Раздел ${page} открыт`);
        }
    });
});

// Dock Items Logic
document.querySelectorAll('.dock-item').forEach(item => {
    item.addEventListener('click', () => {
        const title = item.getAttribute('title');
        addMessage(`Запуск приложения: ${title}`, 'bot');
        // Actual calls are handled by inline onclick in HTML for dock items
    });
});

function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${sender}`;
    msgDiv.textContent = text;
    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}
