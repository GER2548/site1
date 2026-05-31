import json
import os
from flask import Flask, request, render_template_string, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_qaq_key"
USERS_FILE = "users.json"

# --- ПРОГРЕССИЯ ЛИМИТОВ ---
ROW_W = {'A':500, 'B':600, 'C':750, 'D':950, 'E':1200, 'F':1700, 'G':2700, 'H':4200, 'I':6200, 'J':8700}
ROW_V = {'A':2, 'B':3, 'C':5, 'D':8, 'E':13, 'F':21, 'G':34, 'H':55, 'I':89, 'J':144}

# --- СИСТЕМА АВТОРИЗАЦИИ ---
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f: return json.load(f)
        except: pass
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# --- ЛОГИКА СКЛАДА (BACKEND) ---
class SmartWarehouse:
    def __init__(self, username):
        self.username = username
        self.backup_file = f"backup_{username}.json"
        self.rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        self.num_cells = 10
        self.cells = {}
        self.last_error = ""
        self.draft = {"name": "", "qty": "", "price": "", "desc": "", "weight": "", "vol": ""}
        self.load_from_backup()
        self._init_cells()

    def _init_cells(self):
        for r in self.rows:
            for c in range(1, self.num_cells + 1):
                addr = f"{r}{c}"
                if addr not in self.cells:
                    self.cells[addr] = None

    def save_to_backup(self):
        with open(self.backup_file, "w", encoding="utf-8") as f:
            json.dump({"num_cells": self.num_cells, "cells_data": self.cells}, f, ensure_ascii=False, indent=4)

    def load_from_backup(self):
        if os.path.exists(self.backup_file):
            try:
                with open(self.backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "cells_data" in data:
                        self.num_cells = data.get("num_cells", 10)
                        self.cells = data["cells_data"]
                    else:
                        self.cells = data
                        self.num_cells = 10
            except: pass

    def delete_cell(self, addr):
        if addr in self.cells:
            self.cells[addr] = None
            self.save_to_backup()

    def add_item(self, addr, name, qty, price, desc, weight, vol):
        self.last_error = ""
        self.draft = {"name": name, "qty": qty, "price": price, "desc": desc, "weight": weight, "vol": vol}
        addr = addr.upper().strip()
        
        if addr not in self.cells:
            self.last_error = "ERROR_NOT_EXIST"
            return False
        if self.cells[addr] is not None:
            self.last_error = "ERROR_OCCUPIED"
            return False

        row_letter = addr[0]
        max_w = ROW_W.get(row_letter, 500)
        max_v = ROW_V.get(row_letter, 2)

        try:
            q, w, v = int(qty), float(weight), float(vol)
            if (q * w) > max_w or (q * v) > max_v:
                fit_w = int(max_w // w) if w > 0 else q
                fit_v = int(max_v // v) if v > 0 else q
                self.last_error = f"OVERFLOW|{q - min(fit_w, fit_v)}"
                return False

            self.cells[addr] = {"name": name, "qty": q, "price": float(price), "desc": desc or "-", "weight": w, "vol": v}
            self.save_to_backup()
            self.draft = {k: "" for k in self.draft}
            return True
        except:
            self.last_error = "ERROR_INVALID_DATA"
            return False

    def get_row_stats(self):
        stats = {r: {'w': 0, 'v': 0, 'max_w': ROW_W[r], 'max_v': ROW_V[r]} for r in self.rows}
        for addr, item in self.cells.items():
            if item:
                stats[addr[0]]['w'] += item['qty'] * item['weight']
                stats[addr[0]]['v'] += item['qty'] * item['vol']
        return stats

def get_wh():
    if 'user' in session: return SmartWarehouse(session['user'])
    return None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>QAQ Smart Storage</title>
    <style>
        :root {
            --bg-page: #F0F8FF; --bg-card: #ffffff; --bg-input: #f9f9f9;
            --text-main: #333333; --text-muted: #666666; --accent: #00BFFF; --accent-dark: #0088cc;
            --cell-empty: #E1F5FE; --border: #ddd; --danger: #ff4757; --footer-text: #87CEEB;
        }
        [data-theme="dark"] {
            --bg-page: #121212; --bg-card: #1e1e1e; --bg-input: #2d2d2d;
            --text-main: #e0e0e0; --text-muted: #aaaaaa; --accent: #bb86fc; --accent-dark: #9965f4;
            --cell-empty: #333333; --border: #444; --danger: #cf6679; --footer-text: #9575cd;
        }

        body { font-family: 'Segoe UI', sans-serif; background: var(--bg-page); color: var(--text-main); margin: 0; padding: 20px; transition: 0.3s; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; max-width: 1250px; margin-inline: auto; }
        .lang-btn, .nav-btn { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main); padding: 6px 12px; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; }
        .lang-btn:hover, .nav-btn:hover { background: var(--bg-input); }

        .container { max-width: 1250px; width: 100%; margin: 0 auto; background: var(--bg-card); padding: 30px; border-radius: 24px; box-shadow: 0 15px 50px rgba(0,0,0,0.1); box-sizing: border-box; }

        .header-section { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 30px; position: relative; }
        .col-control { display: flex; align-items: center; gap: 10px; background: var(--bg-input); padding: 10px 15px; border-radius: 10px; border: 1px solid var(--border); }
        .col-control input { width: 50px; border: 1px solid var(--border); border-radius: 4px; padding: 4px; background: var(--bg-card); color: var(--text-main); font-weight: bold; outline: none; }
        .col-control button { background: var(--accent); color: white; border: none; border-radius: 4px; padding: 5px 10px; cursor: pointer; font-weight: bold; }
        
        .search-wrapper { position: relative; width: 350px; max-width: 100%; }
        .search-box { padding: 12px; border: 2px solid var(--accent); border-radius: 10px; width: 100%; box-sizing: border-box; background: var(--bg-input); color: var(--text-main); outline: none; }
        .search-results { position: absolute; top: 110%; left: 0; width: 100%; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); max-height: 300px; overflow-y: auto; display: none; z-index: 100; }
        .search-item { padding: 12px 15px; border-bottom: 1px solid var(--border); cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
        .search-item:hover { background: var(--bg-input); }
        
        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; background: var(--bg-input); padding: 20px; border-radius: 16px; margin-bottom: 30px; }
        .form-row input { padding: 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-main); font-size: 13px; width: 100%; box-sizing: border-box; }
        .btn-submit { background: var(--accent); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; height: 38px; }

        .warehouse-layout { display: flex; flex-direction: column; gap: 15px; margin: 30px 0; }
        .row-container { display: flex; background: var(--bg-input); border-radius: 16px; border: 1px solid var(--border); overflow: hidden; min-height: 125px; }
        .row-info { width: 140px; padding: 15px; background: rgba(0, 191, 255, 0.1); border-right: 1px solid var(--border); display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; flex-shrink: 0; }
        .row-info h2 { margin: 0 0 5px 0; font-size: 28px; color: var(--accent); }
        .row-info div { font-size: 11px; font-weight: bold; color: var(--text-muted); line-height: 1.5; }
        .row-info span { color: var(--text-main); font-size: 12px; }
        
        .cells-grid { display: flex; flex-wrap: wrap; gap: 10px; padding: 15px; flex: 1; align-content: flex-start; }
        
        .cell { 
            width: 90px; height: 90px; background: var(--cell-empty); border: 1px solid var(--accent); border-radius: 12px; 
            font-size: 10px; display: flex; align-items: center; justify-content: center; flex-direction: column; 
            cursor: pointer; transition: 0.2s; position: relative; text-align: center; padding: 5px; box-sizing: border-box; overflow: hidden;
        }
        .cell:hover { transform: scale(1.05); z-index: 5; box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .occupied { color: #fff !important; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
        .cell-addr { position:absolute; top:4px; left:4px; opacity:0.6; font-size:9px; font-weight: bold; }

        .auth-modal { max-width: 400px; margin: 50px auto; background: var(--bg-card); padding: 40px; border-radius: 20px; box-shadow: 0 15px 50px rgba(0,0,0,0.15); text-align: center; border: 2px solid var(--accent); }
        .auth-modal input { width: 100%; padding: 15px; margin-bottom: 15px; border: 1px solid var(--border); border-radius: 10px; box-sizing: border-box; background: var(--bg-input); color: var(--text-main); }
        .auth-modal button { width: 100%; padding: 15px; margin-bottom: 10px; background: var(--accent); color: white; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 16px; }
        .auth-modal button.secondary { background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border); }

        .table-view { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }
        .table-view th { background: var(--bg-input); padding: 12px; text-align: left; }
        .table-view td { padding: 12px; border-bottom: 1px solid var(--border); }
        footer { margin-top: 50px; padding: 30px; text-align: center; color: var(--footer-text); border-top: 1px solid var(--border); font-size: 12px; }
    </style>
</head>
<body>

    <div class="top-nav">
        <div class="lang-group">
            <button class="lang-btn" onclick="setLang('ru')">RU</button>
            <button class="lang-btn" onclick="setLang('en')">EN</button>
            <button class="lang-btn" onclick="setLang('cn')">CN</button>
        </div>
        <div>
            <button class="lang-btn" onclick="toggleTheme()">🌓</button>
            {% if session.get('user') %}
                <a href="/logout" class="nav-btn" style="margin-left: 10px;" data-key="btn_logout">Выйти</a>
            {% endif %}
        </div>
    </div>

    {% if not session.get('user') %}
    <div class="auth-modal">
        <h2 style="color: var(--accent);" data-key="auth_title">Вход в систему</h2>
        {% if auth_error %}
            <p style="color: var(--danger); font-weight: bold;" data-key="{{ auth_error }}">{{ auth_error }}</p>
        {% endif %}
        <form action="/auth" method="POST">
            <input name="username" placeholder="Логин (Login)" value="{{ last_user or '' }}" required autocomplete="off">
            <input name="password" type="password" placeholder="Пароль (Password)" required>
            
            {% if show_register %}
                <p style="font-size: 12px; color: var(--text-muted);" data-key="auth_not_found">Пользователь не найден. Создать новый бэкап или попробовать снова?</p>
                <button type="submit" name="action" value="register" data-key="auth_create">Создать новый бэкап</button>
                <button type="submit" name="action" value="login" class="secondary" data-key="auth_try_again">Попробовать снова</button>
            {% else %}
                <button type="submit" name="action" value="login" data-key="auth_login">Войти / Открыть бэкап</button>
            {% endif %}
        </form>
    </div>
    
    {% else %}
    <div class="container">
        <div class="header-section">
            <h1 id="t-title" style="color:var(--accent); margin:0;">QAQ Smart Storage</h1>
            
            <form action="/update_cells" method="POST" class="col-control">
                <span data-key="l_cols" style="font-size: 12px; font-weight: bold; color: var(--text-muted);">Ячеек в ряду:</span>
                <input type="number" name="num_cells" min="1" max="50" value="{{ warehouse.num_cells }}">
                <button type="submit">OK</button>
            </form>

            <div class="search-wrapper">
                <input type="text" id="search" class="search-box" oninput="doSearch()" autocomplete="off">
                <div id="search-results" class="search-results"></div>
            </div>
        </div>

        {% if error %}
        <div style="background: rgba(255, 71, 87, 0.1); color: var(--danger); padding: 15px; border-radius: 12px; margin-bottom: 20px; border-left: 5px solid var(--danger);">
            {% if "OVERFLOW" in error %}
                <span data-key="err_overflow">Ошибка: Переполнение! Лишних:</span> {{ error.split('|')[1] }}
            {% else %} <span data-key="{{ error }}">{{ error }}</span> {% endif %}
        </div>
        {% endif %}

        <form action="/add" method="post" class="form-row" id="add-form">
            <input name="addr" id="p-addr" required maxlength="4">
            <input name="name" id="p-name" required value="{{ draft.name }}">
            <input name="qty" id="p-qty" type="number" required value="{{ draft.qty }}">
            <input name="price" id="p-price" type="number" step="0.01" required value="{{ draft.price }}">
            <input name="weight" id="p-weight" type="number" step="0.1" required value="{{ draft.weight }}">
            <input name="vol" id="p-vol" type="number" step="0.01" required value="{{ draft.vol }}">
            <input name="desc" id="p-desc" value="{{ draft.desc }}">
            <input type="hidden" name="base_price" id="base_price">
            <button type="submit" class="btn-submit" id="p-btn" onclick="prepareSubmit()">OK</button>
        </form>

        <div class="warehouse-layout">
            {% for r in warehouse.rows %}
            {% set stat = row_stats[r] %}
            <div class="row-container">
                <div class="row-info">
                    <h2>{{ r }}</h2>
                    <div><span class="w-val">{{ stat.w|round(1) }}</span> / {{ stat.max_w }} <span data-key="u_kg">кг</span></div>
                    <div><span class="v-val">{{ stat.v|round(3) }}</span> / {{ stat.max_v }} <span data-key="u_m3">м³</span></div>
                </div>
                <div class="cells-grid">
                    {% for c in range(1, warehouse.num_cells + 1) %}
                        {% set addr = r ~ c|string %}
                        {% set item = warehouse.cells.get(addr) %}
                        
                        {% if item %}
                            {% set w_ratio = (item.qty * item.weight) / stat.max_w %}
                            <div class="cell occupied dynamic-bg" data-ratio="{{ w_ratio if w_ratio <= 1 else 1 }}" onclick="askDelete('{{ addr }}')">
                                <span class="cell-addr" style="color:rgba(255,255,255,0.7);">{{ addr }}</span>
                                <div style="font-weight:bold; margin-bottom:2px; font-size:12px;">{{ item.name }}</div>
                                <div style="opacity:0.9;">{{ item.qty }} <span data-key="u_pcs">шт.</span></div>
                                <div style="font-size:10px; margin-top:2px; border-top:1px solid rgba(255,255,255,0.3); padding-top:2px;">
                                    <span class="price-val" data-base="{{ item.price }}">{{ item.price }}</span> <span class="cur-symbol">₽</span>
                                </div>
                            </div>
                        {% else %}
                            <div class="cell" onclick="setCell('{{ addr }}')">
                                <span class="cell-addr">{{ addr }}</span>
                            </div>
                        {% endif %}
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>

        <table class="table-view" id="mainTable">
            <thead>
                <tr>
                    <th data-key="th_addr">Ячейка</th>
                    <th data-key="th_name">Товар</th>
                    <th data-key="th_qty">Кол-во</th>
                    <th data-key="th_price_table">Цена</th>
                    <th data-key="th_weight">Вес (кг)</th>
                    <th data-key="th_vol">Объем (м³)</th>
                </tr>
            </thead>
            <tbody>
                {% for addr, item in warehouse.cells.items() if item %}
                <tr>
                    <td><b>{{ addr }}</b></td>
                    <td>{{ item.name }}</td>
                    <td>{{ item.qty }}</td>
                    <td><span class="price-val" data-base="{{ item.price }}">{{ item.price }}</span> <span class="cur-symbol">₽</span></td>
                    <td>{{ (item.qty * item.weight)|round(1) }}</td>
                    <td>{{ (item.qty * item.vol)|round(3) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <footer>
        <div style="font-weight:bold; font-size:15px; margin-bottom: 10px;">QAQ Team (РФМЛИ)</div>
        <div style="display:flex; justify-content:center; gap:40px; flex-wrap:wrap;">
            <div><b>Кутаев Магомедрасуслик (ItsJustMp4_)</b> (6 кл.) </br> TG:@ItsJustMp4_</br>HEXAGON❤</div>
            <div><b>Алавов Биймурадик (GER)</b> (8 кл.)</br>TG:GER2548</br>DOTA_2❤</div>
            <div><b>Кунтуганов Ратмирчик (Ambassador of C++)</b> (8 кл.)</br>TG: C_plus_plus_is_good</br>Омнисия❤</div>
        </div>
        </br>
        <div style="font-weight:bold; font-size:15px; margin-bottom: 10px;"> Техподдержка</div>
        <div style="display:flex; justify-content:center; gap:40px; flex-wrap:wrap;">
            <div>+7 928 587 97-74     </br> +7 964 005 96-16<div>
        </div>
    </footer>

    <script>
        const wData = {{ cells_json|safe if cells_json else '{}' }};
        const rates = { ru: 1, en: 0.011, cn: 0.078 };
        const syms = { ru: '₽', en: '$', cn: '¥' };

        const i18n = {
            ru: {
                t_title: "QAQ Умный Склад", p_search: "🔍 Поиск товара или ячейки...", cur: "₽", u_pcs: "шт.", u_kg: "кг", u_m3: "м³",
                p_addr: "Ячейка", p_name: "Название", p_qty: "Кол-во", p_price: "Цена",
                p_weight: "Вес кг/шт", p_vol: "Объем м3/шт", p_desc: "Описание", p_btn: "ОК",
                th_addr: "Место", th_name: "Товар", th_qty: "Кол-во", th_price_table: "Цена", th_weight: "Вес (кг)", th_vol: "Объем (м³)",
                err_overflow: "Переполнение! Лишних: ", ERROR_OCCUPIED: "Занято!", ERROR_NOT_EXIST: "Нет ячейки!",
                l_cols: "Ячеек в ряду:", p_no_res: "Ничего не найдено", btn_logout: "Выйти",
                auth_title: "Вход в систему", auth_not_found: "Пользователь не найден. Создать бэкап?",
                auth_create: "Создать новый бэкап", auth_try_again: "Попробовать снова", auth_login: "Войти / Открыть бэкап",
                "Неверный пароль": "Неверный пароль", "Пользователь не найден": "Пользователь не найден"
            },
            en: {
                t_title: "QAQ Smart Storage", p_search: "🔍 Search item or cell...", cur: "$", u_pcs: "pcs", u_kg: "kg", u_m3: "m³",
                p_addr: "Cell", p_name: "Name", p_qty: "Qty", p_price: "Price",
                p_weight: "Weight kg", p_vol: "Vol m3", p_desc: "Desc", p_btn: "OK",
                th_addr: "Addr", th_name: "Item", th_qty: "Qty", th_price_table: "Price", th_weight: "Weight", th_vol: "Volume",
                err_overflow: "Overflow! Excess: ", ERROR_OCCUPIED: "Occupied!", ERROR_NOT_EXIST: "No cell!",
                l_cols: "Cells per row:", p_no_res: "No results found", btn_logout: "Logout",
                auth_title: "System Login", auth_not_found: "User not found. Create backup?",
                auth_create: "Create new backup", auth_try_again: "Try again", auth_login: "Login / Open Backup",
                "Неверный пароль": "Invalid password", "Пользователь не найден": "User not found"
            },
            cn: {
                t_title: "QAQ 智能仓库", p_search: "🔍 搜索物品或位置...", cur: "¥", u_pcs: "件", u_kg: "公斤", u_m3: "立方米",
                p_addr: "位置", p_name: "名称", p_qty: "数量", p_price: "价格",
                p_weight: "单重", p_vol: "体积", p_desc: "备注", p_btn: "确定",
                th_addr: "地址", th_name: "项目", th_qty: "数量", th_price_table: "价格", th_weight: "重量", th_vol: "体积",
                err_overflow: "空间不足! 盈余: ", ERROR_OCCUPIED: "被占用!", ERROR_NOT_EXIST: "无此位置!",
                l_cols: "每行单元格:", p_no_res: "未找到结果", btn_logout: "登出",
                auth_title: "系统登录", auth_not_found: "未找到用户。创建备份？",
                auth_create: "创建新备份", auth_try_again: "再试一次", auth_login: "登录/打开备份",
                "Неверный пароль": "密码无效", "Пользователь не найден": "未找到用户"
            }
        };

        function setLang(lang) {
            localStorage.setItem('lang', lang);
            const d = i18n[lang];
            const r = rates[lang];
            
            if(document.getElementById('t-title')) document.getElementById('t-title').innerText = d.t_title;
            if(document.getElementById('search')) document.getElementById('search').placeholder = d.p_search;
            if(document.getElementById('p-addr')) document.getElementById('p-addr').placeholder = d.p_addr;
            if(document.getElementById('p-name')) document.getElementById('p-name').placeholder = d.p_name;
            if(document.getElementById('p-qty')) document.getElementById('p-qty').placeholder = d.p_qty;
            if(document.getElementById('p-price')) document.getElementById('p-price').placeholder = d.p_price;
            if(document.getElementById('p-weight')) document.getElementById('p-weight').placeholder = d.p_weight;
            if(document.getElementById('p-vol')) document.getElementById('p-vol').placeholder = d.p_vol;
            if(document.getElementById('p-desc')) document.getElementById('p-desc').placeholder = d.p_desc;
            if(document.getElementById('p-btn')) document.getElementById('p-btn').innerText = d.p_btn;
            
            document.querySelectorAll('.cur-symbol').forEach(el => el.innerText = d.cur);
            document.querySelectorAll('.price-val').forEach(el => {
                let base = parseFloat(el.getAttribute('data-base'));
                el.innerText = (base * r).toFixed(2);
            });
            document.querySelectorAll('[data-key]').forEach(el => { if(d[el.getAttribute('data-key')]) el.innerText = d[el.getAttribute('data-key')]; });
            
            doSearch();
        }

        function toggleTheme() {
            const b = document.body;
            const isDark = b.getAttribute('data-theme') === 'dark';
            b.setAttribute('data-theme', isDark ? 'light' : 'dark');
            localStorage.setItem('theme', isDark ? 'light' : 'dark');
            applyColors();
        }

        function applyColors() {
            const isDark = document.body.getAttribute('data-theme') === 'dark';
            document.querySelectorAll('.cell.dynamic-bg').forEach(el => {
                const ratio = parseFloat(el.getAttribute('data-ratio')) || 0;
                if (isDark) {
                    const val = Math.floor(51 - (ratio * 34));
                    el.style.background = `rgb(${val}, ${val}, ${val})`;
                    el.style.borderColor = 'rgba(255,255,255,0.1)';
                } else {
                    const lightness = Math.floor(80 - (ratio * 40));
                    el.style.background = `hsl(197, 85%, ${lightness}%)`;
                    el.style.borderColor = 'rgba(0,0,0,0.2)';
                }
            });
        }

        function prepareSubmit() {
            let p = document.getElementById('p-price');
            let lang = localStorage.getItem('lang') || 'ru';
            if(p.value) {
                document.getElementById('base_price').value = (parseFloat(p.value) / rates[lang]).toFixed(2);
                p.name = ""; 
                document.getElementById('base_price').name = "price";
            }
        }

        function setCell(a) { document.getElementById('p-addr').value = a; }
        function askDelete(a) { if(confirm("Очистить " + a + "?")) window.location.href="/delete/"+a; }
        
        function doSearch() {
            let box = document.getElementById("search");
            if(!box) return;
            let q = box.value.toUpperCase().trim();
            let res = document.getElementById("search-results");
            let lang = localStorage.getItem('lang') || 'ru';
            
            if (!q) { res.style.display = "none"; return; }
            res.style.display = "block";
            res.innerHTML = "";
            let found = false;
            
            for (let addr in wData) {
                let item = wData[addr];
                if (item && (addr.includes(q) || item.name.toUpperCase().includes(q))) {
                    let priceConverted = (item.price * rates[lang]).toFixed(2);
                    res.innerHTML += `
                        <div class="search-item" onclick="setCell('${addr}'); document.getElementById('search-results').style.display='none';">
                            <div><b style="color:var(--accent);">${addr}</b> - ${item.name}</div>
                            <div style="font-size:12px; color:var(--text-muted);">${item.qty} ${i18n[lang].u_pcs} / ${priceConverted}${syms[lang]}</div>
                        </div>`;
                    found = true;
                }
            }
            if (!found) res.innerHTML = `<div class="search-item" style="justify-content:center; color:var(--text-muted);">${i18n[lang].p_no_res}</div>`;
        }

        document.addEventListener('click', function(e) {
            let res = document.getElementById('search-results');
            if(res && !e.target.closest('.search-wrapper')) res.style.display = 'none';
        });

        window.onload = () => {
            setLang(localStorage.getItem('lang') || 'ru');
            if(localStorage.getItem('theme') === 'dark') document.body.setAttribute('data-theme', 'dark');
            applyColors();
        };
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    wh = get_wh()
    if not wh:
        return render_template_string(HTML_TEMPLATE, show_register=False)
    
    cells_json = json.dumps(wh.cells, ensure_ascii=False)
    return render_template_string(HTML_TEMPLATE, warehouse=wh, row_stats=wh.get_row_stats(), error=wh.last_error, draft=wh.draft, cells_json=cells_json)

@app.route('/auth', methods=['POST'])
def auth():
    username = request.form['username'].strip()
    password = request.form['password']
    action = request.form['action']
    users = load_users()

    if action == 'register':
        # Хешируем пароль перед сохранением
        users[username] = generate_password_hash(password)
        save_users(users)
        session['user'] = username
        SmartWarehouse(username).save_to_backup()
        return redirect('/')

    if action == 'login':
        if username in users:
            # Проверяем хешированный пароль
            if check_password_hash(users[username], password):
                session['user'] = username
                return redirect('/')
            else:
                return render_template_string(HTML_TEMPLATE, auth_error="Неверный пароль", show_register=False, last_user=username)
        else:
            return render_template_string(HTML_TEMPLATE, auth_error="Пользователь не найден", show_register=True, last_user=username)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/update_cells', methods=['POST'])
def update_cells():
    wh = get_wh()
    if wh:
        wh.num_cells = int(request.form['num_cells'])
        wh._init_cells()
        wh.save_to_backup()
    return redirect('/')

@app.route('/add', methods=['POST'])
def add():
    wh = get_wh()
    if wh:
        wh.add_item(
            request.form['addr'], request.form['name'], request.form['qty'], 
            request.form['price'], request.form.get('desc', ''), 
            request.form.get('weight', 0), request.form.get('vol', 0)
        )
    return redirect('/')

@app.route('/delete/<addr>')
def delete(addr):
    wh = get_wh()
    if wh: wh.delete_cell(addr)
    return redirect('/')

if __name__ == '__main__':
    app.run(port=5001, debug=True)