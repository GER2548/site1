import json
import os
import random
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_qaq_key"
USERS_FILE = "users.json"

# --- ДЕФОЛТНЫЕ ЛИМИТЫ ---
DEFAULT_LIMITS = {
    'A': {'w': 500, 'v': 2}, 'B': {'w': 600, 'v': 3}, 'C': {'w': 750, 'v': 5},
    'D': {'w': 950, 'v': 8}, 'E': {'w': 1200, 'v': 13}, 'F': {'w': 1700, 'v': 21},
    'G': {'w': 2700, 'v': 34}, 'H': {'w': 4200, 'v': 55}, 'I': {'w': 6200, 'v': 89}, 'J': {'w': 8700, 'v': 144}
}

class SmartWarehouse:
    def __init__(self, username):
        self.username = username
        self.filename = f"backup_{username}.json"
        self.rows = ['A', 'B', 'C', 'D', 'E']
        self.row_configs = {r: {'num_cells': 10} for r in self.rows}
        self.rows_limits = DEFAULT_LIMITS.copy()
        self.cells = {}
        self.clients = {}
        self.orders = {}
        self.history = []
        self.draft = {"addr": "", "name": "", "qty": "", "price": "", "weight": "", "vol": "", "expiry": ""}
        self.load_from_backup()

    def _init_cells(self):
        # Удаляем лишние ячейки, если ряды были изменены
        active_addrs = []
        for r in self.rows:
            count = self.row_configs.get(r, {}).get('num_cells', 10)
            for i in range(1, count + 1):
                active_addrs.append(f"{r}{i}")
        self.cells = {k: v for k, v in self.cells.items() if k in active_addrs}

    def save_to_backup(self):
        data = {
            "cells": self.cells, "clients": self.clients, "orders": self.orders,
            "history": self.history, "rows": self.rows, "row_configs": self.row_configs,
            "rows_limits": self.rows_limits
        }
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_from_backup(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cells = data.get("cells", {})
                    self.clients = data.get("clients", {})
                    self.orders = data.get("orders", {})
                    self.history = data.get("history", [])
                    self.rows = data.get("rows", ['A', 'B', 'C', 'D', 'E'])
                    self.row_configs = data.get("row_configs", {r: {'num_cells': 10} for r in self.rows})
                    self.rows_limits = data.get("rows_limits", DEFAULT_LIMITS.copy())
            except: pass

    def get_row_stats(self):
        stats = {}
        for r in self.rows:
            w_total = sum(float(c['weight']) * int(c['qty']) for k, c in self.cells.items() if k.startswith(r))
            v_total = sum(float(c['vol']) * int(c['qty']) for k, c in self.cells.items() if k.startswith(r))
            stats[r] = {
                'w': w_total, 'v': v_total,
                'max_w': self.rows_limits.get(r, {}).get('w', 500),
                'max_v': self.rows_limits.get(r, {}).get('v', 2)
            }
        return stats

    def get_total_stats(self):
        now = datetime.now()
        expired_count = 0
        total_qty = 0
        total_price = 0
        for c in self.cells.values():
            total_qty += int(c['qty'])
            total_price += float(c['price']) * int(c['qty'])
            if c.get('expiry'):
                try:
                    if datetime.strptime(c['expiry'], '%Y-%m-%d') < now:
                        expired_count += 1
                except: pass
        return {'qty': total_qty, 'price': total_price, 'expired': expired_count}

    def get_expiry_status(self, expiry_str):
        if not expiry_str: return "ok"
        try:
            exp_date = datetime.strptime(expiry_str, '%Y-%m-%d')
            now = datetime.now()
            if exp_date < now: return "expired"
            if exp_date < now + timedelta(days=7): return "expiring_soon"
        except: pass
        return "ok"

# --- FLASK ROUTES ---

def get_wh():
    if 'user' not in session: return None
    return SmartWarehouse(session['user'])

@app.route('/')
def index():
    wh = get_wh()
    if not wh:
        q1, q2 = random.randint(1, 10), random.randint(1, 10)
        session['captcha_res'] = q1 + q2
        return render_template_string(HTML_TEMPLATE, captcha_q=f"{q1}+{q2}")
    
    error_msg = request.args.get('error')
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template_string(HTML_TEMPLATE, 
                                warehouse=wh, 
                                row_stats=wh.get_row_stats(), 
                                total_stats=wh.get_total_stats(), 
                                error=error_msg, 
                                draft=wh.draft, 
                                today=today)

@app.route('/auth', methods=['POST'])
def auth():
    user = request.form.get('username')
    pw = request.form.get('password')
    captcha = request.form.get('captcha')
    action = request.form.get('action')

    if not user or not pw or int(captcha or 0) != session.get('captcha_res'):
        return render_template_string(HTML_TEMPLATE, auth_error="Ошибка данных или капчи", captcha_q="Err")

    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f: users = json.load(f)

    if action == 'register':
        if user in users: return "Пользователь уже есть"
        users[user] = generate_password_hash(pw)
        with open(USERS_FILE, "w") as f: json.dump(users, f)
    
    if user in users and check_password_hash(users[user], pw):
        session['user'] = user
        return redirect('/')
    return "Ошибка входа"

@app.route('/add', methods=['POST'])
def add_item():
    wh = get_wh()
    addr = request.form.get('addr').upper()
    row = addr[0] if addr else ''
    
    if addr in wh.cells: return redirect('/?error=ERROR_OCCUPIED')
    if row not in wh.rows: return redirect('/?error=ERROR_NOT_EXIST')

    try:
        qty = int(request.form.get('qty'))
        weight = float(request.form.get('weight'))
        vol = float(request.form.get('vol'))
        
        # Проверка лимитов ряда
        stats = wh.get_row_stats()[row]
        if (stats['w'] + weight * qty) > stats['max_w']:
            return redirect(f'/?error=OVERFLOW|w|{row}')
        if (stats['v'] + vol * qty) > stats['max_v']:
            return redirect(f'/?error=OVERFLOW|v|{row}')

        wh.cells[addr] = {
            "name": request.form.get('name'), "qty": qty,
            "price": request.form.get('price'), "weight": weight,
            "vol": vol, "expiry": request.form.get('expiry')
        }
        wh.history.append({"date": datetime.now().strftime("%H:%M:%S"), "type": "supply", "desc": f"Ввоз {wh.cells[addr]['name']} в {addr}", "amount": 0})
        wh.save_to_backup()
    except: return redirect('/?error=ERROR_INVALID_DATA')
    return redirect('/')

@app.route('/add_order', methods=['POST'])
def add_order():
    wh = get_wh()
    client_id = request.form.get('client_id')
    addrs = request.form.getlist('item_addr[]')
    qtys = request.form.getlist('item_qty[]')
    
    if not client_id or not addrs: return redirect('/')
    
    total_amount = 0
    order_items = {}
    
    for addr, q in zip(addrs, qtys):
        if addr in wh.cells and q:
            q = int(q)
            item = wh.cells[addr]
            if int(item['qty']) >= q:
                price_with_markup = float(item['price']) * 1.1
                total_amount += price_with_markup * q
                order_items[addr] = q
                # Списываем
                item['qty'] = int(item['qty']) - q
                if item['qty'] <= 0: del wh.cells[addr]

    if order_items:
        oid = os.urandom(4).hex()
        wh.orders[oid] = {"client_id": client_id, "items": order_items, "amount": total_amount, "status": "pending", "paid": False}
        wh.history.append({"date": datetime.now().strftime("%H:%M:%S"), "type": "sale", "desc": f"Заказ {oid} для {client_id}", "amount": total_amount})
        wh.save_to_backup()
    return redirect('/')

@app.route('/add_client', methods=['POST'])
def add_client():
    wh = get_wh()
    cid = os.urandom(4).hex()
    wh.clients[cid] = {
        "name": request.form.get('name'), "phone": request.form.get('phone'),
        "email": request.form.get('email'), "address": request.form.get('address'),
        "balance": 0, "total_spent": 0
    }
    wh.save_to_backup()
    return redirect('/')

@app.route('/delete/<addr>')
def delete_item(addr):
    wh = get_wh()
    if addr in wh.cells:
        del wh.cells[addr]
        wh.save_to_backup()
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ===== ЧАСТЬ 5: HTML_TEMPLATE (HTML, CSS, JS) =====

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>QAQ Smart Storage</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-page: #F0F8FF; --bg-card: #ffffff; --bg-input: #f9f9f9;
            --text-main: #333333; --accent: #00BFFF; --cell-empty: #E1F5FE; --border: #ddd; 
            --danger: #ff4757; --footer-text: #87CEEB; --warning: #ffa502; --success: #2ed573;
        }
        [data-theme="dark"] {
            --bg-page: #121212; --bg-card: #1e1e1e; --bg-input: #2d2d2d;
            --text-main: #e0e0e0; --accent: #9575cd; --cell-empty: #333333; --border: #444; 
            --footer-text: #9575cd; --warning: #ff9800; --success: #05c46b;
        }
        body { font-family: 'Segoe UI', sans-serif; background: var(--bg-page); color: var(--text-main); margin: 0; padding: 20px; transition: 0.3s; }
        .container { max-width: 1300px; width: 100%; margin: 0 auto; background: var(--bg-card); padding: 30px; border-radius: 24px; box-shadow: 0 15px 50px rgba(0,0,0,0.1); box-sizing: border-box; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; max-width: 1300px; margin-inline: auto; flex-wrap: wrap; }
        .lang-btn { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main); padding: 8px 15px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.3s; }
        .lang-btn.active, .lang-btn:hover { background: var(--accent); color: white; }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 30px; border-bottom: 2px solid var(--border); flex-wrap: wrap; }
        .tab-btn { background: none; border: none; color: var(--text-main); padding: 12px 20px; cursor: pointer; font-weight: bold; border-bottom: 3px solid transparent; transition: all 0.3s; font-size: 14px; }
        .tab-btn.active, .tab-btn:hover { color: var(--accent); border-bottom-color: var(--accent); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; background: var(--bg-input); padding: 20px; border-radius: 16px; margin-bottom: 30px; }
        .form-row input, .form-row select { padding: 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-main); font-size: 13px; }

        .row-container { display: flex; background: var(--bg-input); border-radius: 16px; border: 1px solid var(--border); min-height: 125px; margin-bottom: 15px; }
        .row-info { width: 140px; padding: 15px; background: rgba(149, 117, 205, 0.1); border-right: 1px solid var(--border); text-align: center; display: flex; flex-direction: column; justify-content: center; font-size: 12px; }
        .cells-grid { display: flex; flex-wrap: wrap; gap: 10px; padding: 15px; flex: 1; }
        .cell { width: 90px; height: 90px; background: var(--cell-empty); border: 1px solid var(--accent); border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; position: relative; font-size: 11px; text-align: center; }
        .occupied { background: var(--accent) !important; color: white !important; }

        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }
        .stat-card { background: var(--bg-card); padding: 15px; border-radius: 12px; border-left: 4px solid var(--accent); font-size: 13px; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center; }
        .modal-content { background: var(--bg-card); padding: 30px; border-radius: 20px; width: 400px; }

        table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 12px; }
        th { background: var(--bg-input); padding: 10px; text-align: left; border-bottom: 2px solid var(--accent); }
        td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
        
        footer { margin-top: 50px; text-align: center; padding: 20px; border-top: 1px solid var(--border); }
    </style>
</head>
<body onload="initApp()">

{% if not session.get('user') %}
<div style="max-width: 400px; margin: 100px auto; background: var(--bg-card); padding: 40px; border-radius: 20px; text-align: center; border: 2px solid var(--accent);">
    <h2 data-key="auth_title">Вход в систему</h2>
    <form action="/auth" method="POST">
        <input name="username" placeholder="Логин" required style="width:100%; padding:12px; margin-bottom:15px; border-radius:10px; border:1px solid var(--border);">
        <input name="password" type="password" placeholder="Пароль" required style="width:100%; padding:12px; margin-bottom:15px; border-radius:10px; border:1px solid var(--border);">
        <div style="margin-bottom: 15px;">{{ captcha_q }} = <input name="captcha" style="width: 50px;" required></div>
        <button type="submit" name="action" value="login" class="lang-btn" style="width:100%; background:var(--accent); color:white;" data-key="auth_login">Войти</button>
        <button type="submit" name="action" value="register" class="lang-btn" style="width:100%; margin-top:10px;" data-key="auth_create">Регистрация</button>
    </form>
</div>
{% else %}
<div class="top-nav">
    <div id="currency-display" style="font-weight:bold; color:var(--accent);">Валюта: ₽ (RUB)</div>
    <div>
        <button class="lang-btn" id="lang-ru" onclick="setLang('ru')">RU</button>
        <button class="lang-btn" id="lang-en" onclick="setLang('en')">EN</button>
        <button class="lang-btn" id="lang-cn" onclick="setLang('cn')">CN</button>
    </div>
    <div>
        <button class="lang-btn" onclick="toggleTheme()">🌓</button>
        <span style="font-weight: bold;">{{ session.get('user') }}</span>
        <a href="/logout" class="lang-btn" style="background:var(--danger); color:white; text-decoration:none;" data-key="btn_logout">Выход</a>
    </div>
</div>

<div class="container">
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('warehouse')" data-key="tab_warehouse">📦 Склад</button>
        <button class="tab-btn" onclick="switchTab('orders')" data-key="tab_orders">📋 Заказы</button>
        <button class="tab-btn" onclick="switchTab('clients')" data-key="tab_clients">👥 Клиенты</button>
        <button class="tab-btn" onclick="switchTab('stats')" data-key="tab_stats">📈 Статистика</button>
    </div>

    <div id="warehouse" class="tab-content active">
        <form action="/add" method="POST" class="form-row">
            <input name="addr" id="p-addr" placeholder="Ячейка (A1)" required data-key="f_addr">
            <input name="name" placeholder="Товар" required data-key="f_item">
            <input name="qty" type="number" placeholder="Кол-во" required data-key="f_qty">
            <input name="price" type="number" step="0.01" placeholder="Цена" required data-key="f_price">
            <input name="weight" type="number" step="0.01" placeholder="Вес" required data-key="f_weight">
            <input name="vol" type="number" step="0.01" placeholder="Объем" required data-key="f_vol">
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white;" data-key="btn_add">Добавить</button>
        </form>

        {% for r in warehouse.rows %}
        <div class="row-container">
            <div class="row-info">
                <h2>{{ r }}</h2>
                <div style="font-size:10px;">{{ row_stats[r].w|round(1) }} кг / {{ row_stats[r].v|round(1) }} м³</div>
            </div>
            <div class="cells-grid">
                {% for i in range(1, warehouse.row_configs[r].num_cells + 1) %}
                    {% set addr = r ~ i|string %}
                    {% set item = warehouse.cells.get(addr) %}
                    <div class="cell {% if item %}occupied{% endif %}" onclick="openInspector('{{ addr }}')">
                        <span>{{ addr }}</span>
                        {% if item %}<div>{{ item.name }}</div>{% endif %}
                    </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>

    <div id="orders" class="tab-content">
        <form action="/add_order" method="POST" class="form-row">
            <select name="client_id" required>
                <option value="">-- Клиент --</option>
                {% for cid, cl in warehouse.clients.items() %}
                <option value="{{ cid }}">{{ cl.name }}</option>
                {% endfor %}
            </select>
            <input name="item_addr[]" placeholder="Ячейка" required>
            <input name="item_qty[]" type="number" placeholder="Кол-во" required>
            <button type="submit" class="lang-btn" style="background:var(--success); color:white;">Создать заказ</button>
        </form>
        <table>
            <tr><th>ID</th><th>Сумма</th><th>Статус</th></tr>
            {% for oid, ord in warehouse.orders.items() %}
            <tr><td>{{ oid }}</td><td class="money-val" data-val="{{ ord.amount }}">{{ ord.amount }}</td><td>{{ ord.status }}</td></tr>
            {% endfor %}
        </table>
    </div>

    <div id="clients" class="tab-content">
        <form action="/add_client" method="POST" class="form-row">
            <input name="name" placeholder="ФИО" required>
            <input name="phone" placeholder="Телефон" required>
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white;">Добавить</button>
        </form>
        <table>
            <tr><th>Имя</th><th>Телефон</th></tr>
            {% for cid, cl in warehouse.clients.items() %}
            <tr><td>{{ cl.name }}</td><td>{{ cl.phone }}</td></tr>
            {% endfor %}
        </table>
    </div>

    <div id="stats" class="tab-content">
        <div class="stats-grid">
            <div class="stat-card"><h4>Товаров</h4><div class="value">{{ total_stats.qty }}</div></div>
            <div class="stat-card"><h4>Стоимость</h4><div class="value money-val" data-val="{{ total_stats.price }}">{{ total_stats.price }}</div></div>
        </div>
    </div>
</div>

<div id="modal" class="modal-overlay" onclick="closeModal()">
    <div class="modal-content" onclick="event.stopPropagation()">
        <h2 id="m-title"></h2>
        <div id="m-info"></div>
        <button class="lang-btn" style="background:var(--danger); color:white; width:100%; margin-top:20px;" onclick="deleteItem()">Удалить</button>
    </div>
</div>

<footer>QAQ Smart Storage © 2026</footer>
{% endif %}

<script>
const translations = {
    ru: {
        auth_title: "Вход в систему", auth_login: "Войти", auth_create: "Регистрация",
        tab_warehouse: "📦 Склад", tab_orders: "📋 Заказы", tab_clients: "👥 Клиенты", tab_stats: "📈 Статистика",
        f_addr: "Ячейка (A1)", f_item: "Товар", f_qty: "Кол-во", f_price: "Цена", f_weight: "Вес", f_vol: "Объем",
        btn_add: "Добавить", btn_logout: "Выход", curr_name: "Валюта: ₽ (RUB)", curr_sym: "₽"
    },
    en: {
        auth_title: "Login", auth_login: "Login", auth_create: "Register",
        tab_warehouse: "📦 Warehouse", tab_orders: "📋 Orders", tab_clients: "👥 Clients", tab_stats: "📈 Stats",
        f_addr: "Cell (A1)", f_item: "Item", f_qty: "Qty", f_price: "Price", f_weight: "Weight", f_vol: "Volume",
        btn_add: "Add", btn_logout: "Logout", curr_name: "Currency: $ (USD)", curr_sym: "$"
    },
    cn: {
        auth_title: "系统登录", auth_login: "登录", auth_create: "注册",
        tab_warehouse: "📦 仓库", tab_orders: "📋 订单", tab_clients: "👥 客户", tab_stats: "📈 统计",
        f_addr: "单元格 (A1)", f_item: "货物", f_qty: "数量", f_price: "价格", f_weight: "重量", f_vol: "体积",
        btn_add: "添加", btn_logout: "登出", curr_name: "货币: ¥ (CNY)", curr_sym: "¥"
    }
};

let currentLang = 'ru';
let exchangeRate = 1.0;

function initApp() {
    setLang(localStorage.getItem('lang') || 'ru');
}

function setLang(lang) {
    currentLang = lang;
    localStorage.setItem('lang', lang);
    exchangeRate = (lang === 'en') ? 0.011 : (lang === 'cn' ? 0.078 : 1.0);
    
    document.querySelectorAll('[data-key]').forEach(el => {
        const key = el.getAttribute('data-key');
        if (translations[lang][key]) el.innerText = translations[lang][key];
    });

    document.getElementById('currency-display').innerText = translations[lang]['curr_name'];
    document.querySelectorAll('.money-val').forEach(el => {
        const val = parseFloat(el.getAttribute('data-val'));
        el.innerText = (val * exchangeRate).toFixed(2) + ' ' + translations[lang]['curr_sym'];
    });
}

function toggleTheme() {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
}

function switchTab(id) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
}

let activeAddr = '';
function openInspector(addr) {
    activeAddr = addr;
    document.getElementById('m-title').innerText = "Ячейка " + addr;
    document.getElementById('modal').style.display = 'flex';
}

function closeModal() { document.getElementById('modal').style.display = 'none'; }

function deleteItem() {
    if(confirm('Удалить?')) window.location.href = '/delete/' + activeAddr;
}
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(port=5001, debug=True)