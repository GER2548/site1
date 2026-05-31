import json
import os
import random
from flask import Flask, request, render_template_string, send_file

app = Flask(__name__)

# --- ЛОГИКА СКЛАДА ---
class SmartWarehouse:
    def __init__(self):
        self.rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        self.cells = {f"{r}{c}": None for r in self.rows for c in range(1, 11)}
        self.backup_file = "backup_warehouse.json"
        self.draft = {"name": "", "qty": "", "price": "", "desc": ""}
        self.last_error = ""
        self.suggestions = []
        self.load_from_backup()

    def save_to_backup(self):
        with open(self.backup_file, "w", encoding="utf-8") as f:
            json.dump(self.cells, f, ensure_ascii=False, indent=4)

    def load_from_backup(self):
        if os.path.exists(self.backup_file):
            try:
                with open(self.backup_file, "r", encoding="utf-8") as f:
                    self.cells = json.load(f)
            except: pass

    def delete_cell(self, addr):
        if addr in self.cells:
            self.cells[addr] = None
            self.save_to_backup()
            return True
        return False

    def add_item(self, addr, name, qty, price, desc):
        self.last_error = ""
        self.suggestions = []
        self.draft = {"name": name, "qty": qty, "price": price, "desc": desc}
        addr = addr.upper().strip()
        if addr not in self.cells:
            self.last_error = f"Ячейки {addr} нет!"
            return False
        if self.cells[addr] is not None:
            self.last_error = f"Ячейка {addr} занята!"
            free = [k for k, v in self.cells.items() if v is None]
            self.suggestions = random.sample(free, min(3, len(free))) if free else []
            return False
        try:
            self.cells[addr] = {"name": name, "qty": int(qty), "price": float(price), "desc": desc or "-"}
            self.save_to_backup()
            self.draft = {"name": "", "qty": "", "price": "", "desc": ""}
            return True
        except:
            self.last_error = "Ошибка в цифрах!"
            return False

warehouse = SmartWarehouse()

# --- ИНТЕРФЕЙС ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>QAQ Smart Storage</title>
    <style>
        :root { --bg-page: #F0F8FF; --bg-card: #fff; --accent: #00BFFF; --cell-empty: #E1F5FE; --text: #333; --border: #ddd; }
        [data-theme="dark"] { --bg-page: #121212; --bg-card: #1e1e1e; --accent: #bb86fc; --cell-empty: #333; --text: #e0e0e0; --border: #444; }

        body { font-family: 'Segoe UI', sans-serif; background: var(--bg-page); color: var(--text); margin: 0; padding: 20px; transition: 0.3s; }
        
        .theme-switch { position: fixed; top: 15px; left: 15px; z-index: 1001; cursor: pointer; background: var(--bg-card); padding: 8px 12px; border-radius: 20px; border: 1px solid var(--border); font-size: 12px; font-weight: bold; }
        
        .container { max-width: 1100px; margin: 40px auto 0; background: var(--bg-card); padding: 25px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 8px; margin: 20px 0; }
        .cell { aspect-ratio: 1/1; background: var(--cell-empty); border: 1px solid var(--accent); border-radius: 8px; font-size: 10px; display: flex; align-items: center; justify-content: center; flex-direction: column; cursor: pointer; position: relative; }
        .occupied { background: var(--accent) !important; color: white !important; font-weight: bold; }

        .form-panel { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
        .form-panel input { padding: 10px; border: 1px solid var(--border); border-radius: 6px; flex: 1; background: var(--bg-card); color: var(--text); }
        .btn-add { background: var(--accent); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; }

        /* ВИДЕО ОКНО */
        #videoContainer { position: fixed; bottom: 20px; right: 20px; width: 260px; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.5); z-index: 2000; background: #000; border: 2px solid var(--accent); }
        #videoHeader { background: var(--accent); color: white; padding: 6px 12px; display: flex; justify-content: space-between; align-items: center; cursor: move; font-size: 11px; font-weight: bold; }
        .close-btn { cursor: pointer; font-size: 16px; line-height: 1; }
        video { width: 100%; display: block; background: #000; }

        footer { text-align: center; margin-top: 30px; font-size: 11px; opacity: 0.7; }
    </style>
</head>
<body>

    <div class="theme-switch" onclick="toggleTheme()">🌓 <span id="theme-text">Тема</span></div>

    <div class="container">
        <h2 style="color:var(--accent); margin-top:0;">QAQ Smart Storage</h2>
        
        <div class="form-panel">
            <form action="/add" method="post" style="display:contents">
                <input name="addr" placeholder="A1" required maxlength="3" style="max-width: 60px;">
                <input name="name" placeholder="Товар" value="{{ draft.name }}" required>
                <input name="qty" type="number" placeholder="Кол-во" value="{{ draft.qty }}" required>
                <input name="price" type="number" step="0.01" placeholder="Цена" value="{{ draft.price }}" required>
                <input name="desc" placeholder="Описание" value="{{ draft.desc }}">
                <button type="submit" class="btn-add">Добавить</button>
            </form>
        </div>

        <div class="grid">
            {% for addr, item in cells.items() %}
                <div class="cell {{ 'occupied' if item else '' }}" 
                     onclick="{{ 'askDelete(\"' + addr + '\")' if item else 'document.getElementsByName(\"addr\")[0].value=\"' + addr + '\"' }}">
                    <span style="position:absolute; top:2px; left:2px; opacity:0.4; font-size:7px;">{{ addr }}</span>
                    {% if item %} <div>{{ item.name }}</div> {% endif %}
                </div>
            {% endfor %}
        </div>
    </div>

    <footer>QAQ Team: Кутаев, Алавов, Кунтуганов | РФМЛИ</footer>

    <div id="videoContainer">
        <div id="videoHeader">
            <span>📺 Live Monitor</span>
            <span class="close-btn" onclick="this.parentElement.parentElement.remove()">×</span>
        </div>
        <video autoplay muted loop playsinline id="mainVideo">
            <source src="/video_feed" type="video/mp4">
        </video>
    </div>

    <script>
        function toggleTheme() {
            const b = document.body;
            const isDark = b.getAttribute('data-theme') === 'dark';
            b.setAttribute('data-theme', isDark ? 'light' : 'dark');
            localStorage.setItem('theme', isDark ? 'light' : 'dark');
        }
        if(localStorage.getItem('theme') === 'dark') document.body.setAttribute('data-theme', 'dark');

        function askDelete(addr) { if(confirm("Удалить из " + addr + "?")) window.location.href="/delete/"+addr; }

        // Drag and Drop логика
        const box = document.getElementById("videoContainer");
        const head = document.getElementById("videoHeader");
        let active = false, startX, startY, xOff = 0, yOff = 0;

        head.onmousedown = (e) => {
            startX = e.clientX - xOff; startY = e.clientY - yOff;
            active = true;
        };
        window.onmouseup = () => active = false;
        window.onmousemove = (e) => {
            if (active) {
                xOff = e.clientX - startX; yOff = e.clientY - startY;
                box.style.transform = `translate(${xOff}px, ${yOff}px)`;
            }
        };

        // Попытка запустить видео, если браузер заблокировал его
        window.onload = () => {
            const v = document.getElementById('mainVideo');
            v.play().catch(() => { console.log("Браузер требует клика для запуска видео"); });
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, cells=warehouse.cells, draft=warehouse.draft)

@app.route('/video_feed')
def video_feed():
    # Находим полный путь к файлу в папке со скриптом
    video_file = os.path.join(os.getcwd(), 'видеомайн.mp4')
    if os.path.exists(video_file):
        return send_file(video_file, mimetype='video/mp4')
    return "Файл не найден", 404

@app.route('/add', methods=['POST'])
def add():
    warehouse.add_item(request.form['addr'], request.form['name'], request.form['qty'], request.form['price'], request.form.get('desc', ''))
    return index()

@app.route('/delete/<addr>')
def delete(addr):
    warehouse.delete_cell(addr)
    return index()

if __name__ == '__main__':
    app.run(port=5001, debug=True)