# ===== ЧАСТЬ 1: ИМПОРТЫ И КОНФИГУРАЦИЯ =====

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
# ===== ЧАСТЬ 2: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
    except:
        pass

def load_clients(username):
    clients_file = f"clients_{username}.json"
    if os.path.exists(clients_file):
        try:
            with open(clients_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_clients(username, clients):
    clients_file = f"clients_{username}.json"
    try:
        with open(clients_file, "w", encoding="utf-8") as f:
            json.dump(clients, f, ensure_ascii=False, indent=4)
    except:
        pass

# ===== ЧАСТЬ 3: КЛАСС SmartWarehouse (часть 1/3) =====

class SmartWarehouse:
    def __init__(self, username):
        self.username = username
        self.backup_file = f"backup_{username}.json"
        self.rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        self.num_cells = 10
        self.cells = {}
        self.rows_limits = DEFAULT_LIMITS.copy()
        self.row_configs = {r: {'num_cells': 10} for r in self.rows}
        self.clients = {}
        self.orders = {}
        self.last_error = ""
        self.draft = {"addr": "", "name": "", "qty": "", "price": "", "weight": "", "vol": "", "expiry": ""}
        self.load_from_backup()
        self.load_clients_data()
        self._init_cells()

    def load_clients_data(self):
        self.clients = load_clients(self.username)
        orders_file = f"orders_{self.username}.json"
        if os.path.exists(orders_file):
            try:
                with open(orders_file, "r", encoding="utf-8") as f:
                    self.orders = json.load(f)
            except:
                self.orders = {}

    def save_clients_data(self):
        save_clients(self.username, self.clients)

    def save_orders_data(self):
        orders_file = f"orders_{self.username}.json"
        try:
            with open(orders_file, "w", encoding="utf-8") as f:
                json.dump(self.orders, f, ensure_ascii=False, indent=4)
        except:
            pass

    def _init_cells(self):
        for r in self.rows:
            # Безопасное получение (исправление KeyError)
            if r not in self.row_configs:
                self.row_configs[r] = {'num_cells': 10}
            num_cells = self.row_configs[r].get('num_cells', 10)
            for c in range(1, num_cells + 1):
                addr = f"{r}{c}"
                if addr not in self.cells:
                    self.cells[addr] = None

    def save_to_backup(self):
        data = {
            "num_cells": self.num_cells,
            "cells_data": self.cells,
            "limits": self.rows_limits,
            "row_configs": self.row_configs,
            "rows": self.rows # Теперь сохраняем и активные ряды!
        }
        try:
            with open(self.backup_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except:
            pass

    def load_from_backup(self):
        if os.path.exists(self.backup_file):
            try:
                with open(self.backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.num_cells = data.get("num_cells", 10)
                    self.cells = data.get("cells_data", {})
                    # Корректно загружаем сохраненные ряды, если есть
                    self.rows = data.get("rows", ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'])
                    self.rows_limits = data.get("limits", DEFAULT_LIMITS.copy())
                    self.row_configs = data.get("row_configs", {r: {'num_cells': 10} for r in self.rows})
            except:
                pass

# ===== ЧАСТЬ 4: КЛАСС SmartWarehouse (часть 2/3) =====

    def add_client(self, name, phone, email, address):
        try:
            if not name or not phone:
                self.last_error = "ERROR_INVALID_DATA"
                return False
            
            client_id = str(int(datetime.now().timestamp() * 1000))
            self.clients[client_id] = {
                "name": name.strip(),
                "phone": phone.strip(),
                "email": email.strip(),
                "address": address.strip(),
                "created": datetime.now().isoformat(),
                "balance": 0.0,
                "total_spent": 0.0,
                "orders": [],
                "returns": []
            }
            self.save_clients_data()
            return True
        except Exception:
            self.last_error = "ERROR_INVALID_DATA"
            return False

    def add_item(self, addr, name, qty, price, weight, vol, expiry=""):
        self.last_error = ""
        addr = addr.upper().strip()
        
        try:
            q = int(qty)
            p = float(price)
            w = float(weight)
            v = float(vol)
        except (ValueError, TypeError):
            self.last_error = "ERROR_INVALID_DATA"
            return False
        
        if not addr or not name or q <= 0 or p < 0 or w < 0 or v < 0:
            self.last_error = "ERROR_INVALID_DATA"
            return False
        
        if len(addr) < 2:
            self.last_error = "ERROR_INVALID_ADDR"
            return False
        
        if expiry:
            try:
                datetime.strptime(expiry, '%Y-%m-%d')
            except ValueError:
                self.last_error = "ERROR_INVALID_DATE"
                return False
        
        self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
        
        if addr not in self.cells:
            self.last_error = "ERROR_NOT_EXIST"
            return False
        if self.cells[addr]:
            self.last_error = "ERROR_OCCUPIED"
            return False
        
        # Безопасное получение лимитов
        lim = self.rows_limits.get(addr[0], DEFAULT_LIMITS.get(addr[0], {'w': 500, 'v': 2}))
        
        if (q * w) > lim['w'] or (q * v) > lim['v']:
            self.last_error = f"OVERFLOW|{q}|{addr[0]}"
            return False
        
        self.cells[addr] = {
            "name": name,
            "qty": q,
            "price": p,
            "weight": w,
            "vol": v,
            "expiry": expiry if expiry else None,
            "added": datetime.now().isoformat()
        }
        self.save_to_backup()
        self.draft = {k: "" for k in self.draft}
        return True

# ===== ЧАСТЬ 5: КЛАСС SmartWarehouse (часть 3/3) =====

    def add_order(self, client_id, order_items_str, amount, status="pending"):
        try:
            if client_id not in self.clients:
                self.last_error = "ERROR_CLIENT_NOT_FOUND"
                return False
            
            order_items = {}
            item_list = order_items_str.split(',')
            
            if not item_list or not item_list[0].strip():
                self.last_error = "ERROR_NO_ITEMS"
                return False
            
            for item_str in item_list:
                item_str = item_str.strip()
                if not item_str or ':' not in item_str:
                    continue
                
                try:
                    parts = item_str.split(':')
                    if len(parts) != 2:
                        self.last_error = f"ERROR_INVALID_FORMAT|{item_str}"
                        return False
                    
                    addr = parts[0].strip().upper()
                    qty_str = parts[1].strip()
                    
                    if not addr or len(addr) < 2:
                        self.last_error = f"ERROR_INVALID_ADDR|{addr}"
                        return False
                    
                    try:
                        qty = int(qty_str)
                        if qty <= 0:
                            self.last_error = f"ERROR_INVALID_QTY|{addr}|{qty}"
                            return False
                    except ValueError:
                        self.last_error = f"ERROR_INVALID_QTY|{addr}|{qty_str}"
                        return False
                    
                    if addr not in self.cells:
                        self.last_error = f"ERROR_CELL_NOT_EXIST|{addr}"
                        return False
                    
                    if self.cells[addr] is None:
                        self.last_error = f"ERROR_ITEM_NOT_FOUND|{addr}"
                        return False
                    
                    item_data = self.cells[addr]
                    if item_data['qty'] < qty:
                        self.last_error = f"ERROR_INSUFFICIENT_QTY|{addr}|{qty}|{item_data['qty']}"
                        return False
                    
                    order_items[addr] = qty
                    
                except Exception as e:
                    self.last_error = f"ERROR_PARSE_ITEM|{item_str}"
                    return False
            
            if not order_items:
                self.last_error = "ERROR_NO_ITEMS"
                return False
            
            try:
                amount_float = float(amount)
                if amount_float <= 0:
                    self.last_error = "ERROR_INVALID_AMOUNT"
                    return False
            except (ValueError, TypeError):
                self.last_error = "ERROR_INVALID_AMOUNT"
                return False
            
            order_id = str(int(datetime.now().timestamp() * 1000))
            self.orders[order_id] = {
                "client_id": client_id,
                "items": order_items,
                "amount": amount_float,
                "status": status,
                "created": datetime.now().isoformat(),
                "paid": False
            }
            self.clients[client_id]["orders"].append(order_id)
            self.clients[client_id]["total_spent"] += amount_float
            
            self.save_orders_data()
            self.save_clients_data()
            self.last_error = ""
            return True
            
        except Exception as e:
            self.last_error = f"ERROR_UNKNOWN|{str(e)}"
            return False

    def get_expiry_status(self, expiry_date):
        if not expiry_date:
            return "no_expiry"
        try:
            exp_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            today = datetime.now().date()
            days_left = (exp_date - today).days
            if days_left < 0: return "expired"
            elif days_left <= 3: return "expiring_soon"
            else: return "ok"
        except:
            return "unknown"

    def get_row_stats(self):
        stats = {}
        for r in self.rows:
            # Безопасное получение лимитов
            lim = self.rows_limits.get(r, DEFAULT_LIMITS.get(r, {'w': 500, 'v': 2}))
            stats[r] = {'w': 0, 'v': 0, 'max_w': lim['w'], 'max_v': lim['v']}
            
        for addr, item in self.cells.items():
            if item and addr[0] in stats:
                stats[addr[0]]['w'] += item['qty'] * item['weight']
                stats[addr[0]]['v'] += item['qty'] * item['vol']
        return stats

    def get_total_stats(self):
        total_w = total_v = total_price = total_qty = expired_count = expiring_soon_count = 0
        for item in self.cells.values():
            if item:
                total_w += item['qty'] * item['weight']
                total_v += item['qty'] * item['vol']
                total_price += item['qty'] * item['price']
                total_qty += item['qty']
                status = self.get_expiry_status(item.get('expiry'))
                if status == "expired": expired_count += item['qty']
                elif status == "expiring_soon": expiring_soon_count += item['qty']
        return {'w': total_w, 'v': total_v, 'price': total_price, 'qty': total_qty, 'expired': expired_count, 'expiring_soon': expiring_soon_count}

def get_wh():
    if 'user' in session: return SmartWarehouse(session['user'])
    return None

# ===== ЧАСТЬ 6: HTML_TEMPLATE =====

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>QAQ Smart Storage</title>
    <style>
        :root {
            --bg-page: #F0F8FF; --bg-card: #ffffff; --bg-input: #f9f9f9;
            --text-main: #333333; --accent: #00BFFF; --cell-empty: #E1F5FE; --border: #ddd; --danger: #ff4757; --footer-text: #87CEEB; --warning: #ffa502;
        }
        [data-theme="dark"] {
            --bg-page: #121212; --bg-card: #1e1e1e; --bg-input: #2d2d2d;
            --text-main: #e0e0e0; --accent: #9575cd; --cell-empty: #333333; --border: #444; --footer-text: #9575cd; --warning: #ff9800;
        }
        body { font-family: 'Segoe UI', sans-serif; background: var(--bg-page); color: var(--text-main); margin: 0; padding: 20px; transition: 0.3s; }
        .container { max-width: 1250px; width: 100%; margin: 0 auto; background: var(--bg-card); padding: 30px; border-radius: 24px; box-shadow: 0 15px 50px rgba(0,0,0,0.1); box-sizing: border-box; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; max-width: 1250px; margin-inline: auto; flex-wrap: wrap; }
        .lang-btn { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main); padding: 8px 15px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.3s; }
        .lang-btn.active { background: var(--accent); color: white; }
        .lang-btn:hover { background: var(--bg-input); }
        .lang-btn.active:hover { background: var(--accent); }
        
        .header-section { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 30px; position: relative; }
        .search-wrapper { position: relative; width: 350px; }
        .search-box { padding: 12px; border: 2px solid var(--accent); border-radius: 10px; width: 100%; background: var(--bg-input); color: var(--text-main); outline: none; box-sizing: border-box; }
        .search-dropdown { position: absolute; top: 110%; left: 0; width: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); max-height: 400px; overflow-y: auto; display: none; z-index: 100; }
        .search-item { padding: 12px; border-bottom: 1px solid var(--border); cursor: pointer; font-size: 12px; }
        .search-item:hover { background: var(--bg-input); }

        .tabs { display: flex; gap: 10px; margin-bottom: 30px; border-bottom: 2px solid var(--border); flex-wrap: wrap; }
        .tab-btn { background: none; border: none; color: var(--text-main); padding: 12px 20px; cursor: pointer; font-weight: bold; border-bottom: 3px solid transparent; transition: all 0.3s; font-size: 14px; }
        .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
        .tab-btn:hover { color: var(--accent); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; background: var(--bg-input); padding: 20px; border-radius: 16px; margin-bottom: 30px; }
        .form-row input, .form-row textarea, .form-row select { padding: 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-main); font-size: 13px; box-sizing: border-box; }
        .form-row textarea { grid-column: span 2; resize: vertical; min-height: 60px; }
        .form-row select { cursor: pointer; }
        
        .row-container { display: flex; background: var(--bg-input); border-radius: 16px; border: 1px solid var(--border); min-height: 125px; margin-bottom: 15px; }
        .row-info { width: 140px; padding: 15px; background: rgba(149, 117, 205, 0.1); border-right: 1px solid var(--border); text-align: center; display: flex; flex-direction: column; justify-content: center; font-size: 12px; }
        .cells-grid { display: flex; flex-wrap: wrap; gap: 10px; padding: 15px; flex: 1; }
        .cell { width: 90px; height: 90px; background: var(--cell-empty); border: 1px solid var(--accent); border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; position: relative; font-size: 11px; text-align: center; }
        .cell:hover { transform: scale(1.05); z-index: 5; box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .occupied { background: var(--accent) !important; color: white !important; font-weight: bold; }
        .expired { background: var(--danger) !important; color: white !important; animation: pulse 1s infinite; }
        .expiring-soon { background: var(--warning) !important; color: white !important; animation: pulse-warn 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes pulse-warn { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }

        .settings-panel { display: none; background: var(--bg-input); padding: 20px; border-radius: 16px; margin-bottom: 20px; border: 2px dashed var(--accent); max-height: 400px; overflow-y: auto; }
        .limits-table { width: 100%; border-collapse: collapse; font-size: 12px; }
        .limits-table td, .limits-table th { padding: 8px; border-bottom: 1px solid var(--border); }

        .groups-section { margin-bottom: 30px; }
        .group-controls { display: grid; gap: 15px; }
        .group-row { display: grid; grid-template-columns: 26px 80px 100px 150px 1fr; gap: 10px; align-items: center; background: var(--bg-card); padding: 10px; border-radius: 8px; border: 1px solid var(--border); font-size: 12px; }
        .group-row.dragging { opacity: 0.5; }
        .group-row.drag-over { outline: 2px dashed var(--accent); }
        .drag-handle { cursor: grab; user-select: none; text-align: center; font-size: 16px; color: var(--accent); }
        .group-row button { padding: 6px 10px; border-radius: 6px; border: none; cursor: pointer; font-weight: bold; font-size: 12px; }
        .btn-remove { background: var(--danger); color: white; }
        .btn-remove:hover { opacity: 0.8; }

        .summary-section { background: var(--bg-input); padding: 20px; border-radius: 16px; margin-top: 30px; border: 2px solid var(--accent); }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-top: 15px; }
        .summary-item { background: var(--bg-card); padding: 15px; border-radius: 12px; border-left: 4px solid var(--accent); font-size: 13px; }
        .summary-item h4 { margin: 0 0 10px 0; color: var(--accent); font-size: 11px; text-transform: uppercase; }
        .summary-item .value { font-size: 22px; font-weight: bold; color: var(--text-main); }
        .summary-item .unit { font-size: 11px; color: var(--text-muted); margin-top: 5px; }

        .items-table, .clients-table, .orders-table { width: 100%; border-collapse: collapse; margin-top: 30px; font-size: 12px; }
        .items-table th, .clients-table th, .orders-table th { background: var(--bg-input); padding: 10px; text-align: left; border-bottom: 2px solid var(--accent); font-weight: bold; }
        .items-table td, .clients-table td, .orders-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
        .items-table tr:hover, .clients-table tr:hover, .orders-table tr:hover { background: var(--bg-input); }

        .error-notification { background: rgba(255, 71, 87, 0.1); border: 2px solid var(--danger); color: var(--danger); padding: 15px; border-radius: 12px; margin-bottom: 20px; display: none; font-size: 13px; }
        .error-notification.show { display: block; }
        .warning-notification { background: rgba(255, 165, 2, 0.1); border: 2px solid var(--warning); color: var(--warning); padding: 12px; border-radius: 8px; margin-bottom: 15px; display: none; font-size: 12px; }
        .warning-notification.show { display: block; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(3px); overflow-y: auto; }
        .modal-content { background: var(--bg-card); padding: 30px; border-radius: 20px; width: 450px; border: 2px solid var(--accent); max-height: 90vh; overflow-y: auto; box-sizing: border-box; margin: 20px auto; }

        footer { margin-top: 50px; padding: 30px; text-align: center; color: var(--footer-text); border-top: 1px solid var(--border); font-size: 11px; }

        .user-info { display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
        .username-display { font-weight: bold; color: var(--text-main); font-size: 14px; }
        .logout-btn { background: var(--danger); color: white; padding: 8px 15px; border-radius: 8px; text-decoration: none; cursor: pointer; border: none; font-weight: bold; font-size: 13px; }
        .logout-btn:hover { opacity: 0.8; }

        .auth-error { background: rgba(255, 71, 87, 0.15); border: 2px solid var(--danger); color: var(--danger); padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center; font-weight: bold; font-size: 12px; }

        .expiry-warning { color: var(--danger); font-weight: bold; }
        .expiry-warn-soon { color: var(--warning); font-weight: bold; }
        .action-btn { background: var(--accent); color: white; border: none; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 11px; margin-right: 3px; }
        .action-btn:hover { opacity: 0.8; }
        .action-btn.delete { background: var(--danger); }
    </style>
</head>
<body onload="initApp()">

<div class="top-nav">
    <div>
        <button class="lang-btn" id="lang-ru" onclick="setLang('ru')">RU</button>
        <button class="lang-btn" id="lang-en" onclick="setLang('en')">EN</button>
        <button class="lang-btn" id="lang-cn" onclick="setLang('cn')">CN</button>
    </div>
    <div class="user-info">
        <button class="lang-btn" onclick="toggleTheme()">🌓</button>
        <button class="lang-btn" onclick="toggleSettings()">⚙️</button>
        {% if session.get('user') %}
            <span class="username-display">{{ session.get('user') }}</span>
            <a href="/logout" class="logout-btn" data-key="btn_logout">Выход</a>
        {% endif %}
    </div>
</div>

{% if not session.get('user') %}
<div style="max-width: 400px; margin: 100px auto; background: var(--bg-card); padding: 40px; border-radius: 20px; text-align: center; border: 2px solid var(--accent);">
    <h2 id="auth-title" data-key="auth_title" style="color:var(--accent);">Вход в систему</h2>
    {% if auth_error %}
        <div class="auth-error" id="auth-error-msg">{{ auth_error }}</div>
    {% endif %}
    <form action="/auth" method="POST">
        <input id="auth-username" name="username" placeholder="Логин" value="{{ last_username or '' }}" required style="width:100%; padding:12px; margin-bottom:15px; border-radius:10px; border:1px solid var(--border); box-sizing: border-box;">
        <input id="auth-password" name="password" type="password" placeholder="Пароль" required style="width:100%; padding:12px; margin-bottom:15px; border-radius:10px; border:1px solid var(--border); box-sizing: border-box;">
        <div style="margin-bottom: 15px; font-weight: bold; font-size: 13px; display: flex; justify-content: center; align-items: center; gap: 10px; background: var(--bg-input); padding: 10px; border-radius: 10px;">
            <span style="color:var(--accent); font-size: 16px;">{{ captcha_q }}</span>
            <input name="captcha" style="width: 70px; padding: 8px; border-radius: 6px; border: 1px solid var(--border);" required>
        </div>
        <button type="submit" name="action" value="login" class="lang-btn" style="width:100%; background:var(--accent); color:white;" data-key="auth_login">Войти</button>
        <button type="submit" name="action" value="register" class="lang-btn" style="width:100%; margin-top:10px; background:#666; color:white;" data-key="auth_create">Создать бэкап</button>
    </form>
</div>
{% else %}
<div class="container">

    <div id="settings-panel" class="settings-panel">
        <h3 data-key="set_title">⚙️ Управление лимитами</h3>
        <form id="settings-form" method="POST" action="/update_groups">
            <div class="groups-section">
                <h4 data-key="set_manage_rows">Управление группами</h4>
                <div class="group-controls" id="groups-container"></div>
                <button type="button" onclick="addNewGroup()" class="lang-btn" style="background:var(--accent); color:white; width:100%; margin-top:15px; font-size: 12px;" data-key="set_add_row">Добавить группу</button>
            </div>

            <hr style="border:none; border-top:1px solid var(--border); margin: 20px 0;">

            <h4 data-key="set_limits_title">Лимиты групп</h4>
            <table class="limits-table">
                <tr><th style="font-size: 12px;">Ряд</th><th style="font-size: 12px;">Вес 1шт (кг)</th><th style="font-size: 12px;">Объем 1шт (м³)</th></tr>
                {% for r in warehouse.rows %}
                <tr>
                    <td><b>{{ r }}</b><input type="hidden" name="row_key[]" value="{{ r }}"></td>
                    <td><input type="number" name="row_w[]" value="{{ warehouse.rows_limits.get(r, {}).get('w', 500) }}" style="width:70px; padding: 6px;"></td>
                    <td><input type="number" name="row_v[]" value="{{ warehouse.rows_limits.get(r, {}).get('v', 2) }}" step="0.1" style="width:70px; padding: 6px;"></td>
                </tr>
                {% endfor %}
            </table>
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white; width:100%; margin-top:15px; font-size: 12px;" data-key="set_save">Сохранить всё</button>
        </form>
    </div>

    {% if error %}
    <div class="error-notification" style="display:block;">
        {% if "OVERFLOW" in error %}
            <span data-key="err_overflow">Ошибка: Переполнение! Лишних:</span> {{ error.split('|')[1] }}
        {% else %}
            <span data-key="{{ error }}">{{ error }}</span>
        {% endif %}
    </div>
    {% endif %}

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('warehouse')" data-key="tab_warehouse">📦 Склад</button>
        <button class="tab-btn" onclick="switchTab('clients')" data-key="tab_clients">👥 Клиенты</button>
        <button class="tab-btn" onclick="switchTab('orders')" data-key="tab_orders">📋 Заказы</button>
    </div>

    <div id="warehouse" class="tab-content active">
        <div class="header-section">
            <h1 id="t-title" data-key="t_title" style="color:var(--accent); margin:0; font-size: 24px;">QAQ Smart Storage</h1>
            <div class="search-wrapper">
                <input type="text" id="search" class="search-box" oninput="doSearch()" data-key="search_ph" placeholder="Поиск товара или ячейки...">
                <div id="search-dropdown" class="search-dropdown"></div>
            </div>
        </div>

        <form action="/add" method="POST" class="form-row">
            <input name="addr" id="p-addr" placeholder="Ячейка" required value="{{ draft.addr }}" data-key="f_addr">
            <input name="name" placeholder="Товар" required value="{{ draft.name }}" data-key="f_item">
            <input name="qty" type="number" placeholder="Кол-во" required value="{{ draft.qty }}" data-key="f_qty" min="1">
            <input name="price" type="number" step="0.01" placeholder="Цена" required value="{{ draft.price }}" data-key="f_price" min="0">
            <input name="weight" type="number" step="0.01" placeholder="Вес" required value="{{ draft.weight }}" data-key="f_weight" min="0">
            <input name="vol" type="number" step="0.01" placeholder="Объем" required value="{{ draft.vol }}" data-key="f_vol" min="0">
            <input name="expiry" type="date" placeholder="Срок годности" value="{{ draft.expiry }}" data-key="f_expiry">
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white; font-size: 12px;">OK</button>
        </form>

        <div class="warehouse-layout">
            {% for r in warehouse.rows %}
            {% set stat = row_stats[r] %}
            {% set num_cells_in_row = warehouse.row_configs.get(r, {}).get('num_cells', 10) %}
            <div class="row-container">
                <div class="row-info">
                    <div style="font-size:9px; color:var(--text-muted); margin-bottom:5px;">1 ячейка:<br>{{ stat.max_w }} кг | {{ stat.max_v }} м³</div>
                    <h2 style="margin:0; color:var(--accent); font-size: 22px;">{{ r }}</h2>
                    <div style="font-size:9px; color:var(--text-muted); margin-top:5px; margin-bottom:5px;">Вся группа:<br>{{ stat.max_w * num_cells_in_row }} кг | {{ stat.max_v * num_cells_in_row }} м³</div>
                    <hr style="border:none; border-top:1px solid var(--border); width:100%; margin:5px 0;">
                    <div style="font-size:10px;">Занято:<br>{{ stat.w|round(1) }} кг<br>{{ stat.v|round(2) }} м³</div>
                </div>
                <div class="cells-grid">
                    {% for c in range(1, num_cells_in_row + 1) %}
                        {% set addr = r ~ c|string %}
                        {% set item = warehouse.cells.get(addr) %}
                        {% set exp_status = warehouse.get_expiry_status(item.expiry if item else None) %}
                        <div class="cell {% if item %}occupied{% endif %} {% if exp_status == 'expired' %}expired{% elif exp_status == 'expiring_soon' %}expiring-soon{% endif %}"
                             onclick="{% if item %}openInspector('{{ addr }}', '{{ item.name }}', {{ item.qty }}, {{ item.price }}, '{{ item.expiry or '' }}'){% else %}setCell('{{ addr }}'){% endif %}">
                            <span style="position:absolute; top:3px; left:4px; font-size:9px; opacity:0.6;">{{ addr }}</span>
                            {% if item %}
                                <div style="margin-top:10px; font-size: 10px;">{{ item.name }}</div>
                                <div id="unit-{{ addr }}" class="unit-display" style="font-weight: bold;">{{ item.qty }}</div>
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="summary-section">
            <h3 data-key="summary_title" style="margin-top:0; color:var(--accent);">📊 Смета склада</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <h4 data-key="sum_qty">Общее количество</h4>
                    <div class="value" id="total-qty">{{ total_stats.qty }}</div>
                    <div class="unit" id="unit-qty">шт.</div>
                </div>
                <div class="summary-item">
                    <h4 data-key="sum_weight">Общий вес</h4>
                    <div class="value" id="total-weight">{{ total_stats.w|round(1) }}</div>
                    <div class="unit">кг</div>
                </div>
                <div class="summary-item">
                    <h4 data-key="sum_volume">Общий объем</h4>
                    <div class="value" id="total-volume">{{ total_stats.v|round(2) }}</div>
                    <div class="unit">м³</div>
                </div>
                <div class="summary-item">
                    <h4 data-key="sum_price">Общая стоимость</h4>
                    <div class="value" id="total-price">{{ total_stats.price|round(2) }}</div>
                    <div class="unit" id="price-unit">₽</div>
                </div>
                <div class="summary-item" id="expiry-item" style="border-left-color: var(--danger); display: {% if total_stats.expired > 0 %}block{% else %}none{% endif %};">
                    <h4 data-key="sum_expired">⚠️ Испорчено</h4>
                    <div class="value" style="color: var(--danger);">{{ total_stats.expired }}</div>
                    <div class="unit">шт.</div>
                </div>
                <div class="summary-item" id="expiring-item" style="border-left-color: var(--warning); display: {% if total_stats.expiring_soon > 0 %}block{% else %}none{% endif %};">
                    <h4 data-key="sum_expiring">⏰ Испортится</h4>
                    <div class="value" style="color: var(--warning);">{{ total_stats.expiring_soon }}</div>
                    <div class="unit">шт.</div>
                </div>
            </div>
        </div>

        <h3 data-key="items_list_title" style="margin-top: 30px; color: var(--accent); font-size: 16px;">📋 Список товаров</h3>
        <table class="items-table">
            <thead>
                <tr>
                    <th data-key="th_addr">Ячейка</th>
                    <th data-key="th_item">Товар</th>
                    <th data-key="th_qty_table">Кол-во</th>
                    <th data-key="th_price_table">Цена</th>
                    <th data-key="th_weight_table">Вес (кг)</th>
                    <th data-key="th_vol_table">Объем (м³)</th>
                    <th data-key="th_expiry">Срок</th>
                    <th>Статус</th>
                </tr>
            </thead>
            <tbody>
                {% for addr, item in warehouse.cells.items() if item %}
                {% set exp_status = warehouse.get_expiry_status(item.expiry) %}
                <tr {% if exp_status == 'expired' %}style="background-color: rgba(255, 71, 87, 0.3);"{% elif exp_status == 'expiring_soon' %}style="background-color: rgba(255, 165, 2, 0.2);"{% endif %}>
                    <td><b>{{ addr }}</b></td>
                    <td>{{ item.name }}</td>
                    <td><span class="qty-display">{{ item.qty }}</span> <span class="unit-label">шт.</span></td>
                    <td>{{ item.price }}</td>
                    <td>{{ (item.qty * item.weight)|round(1) }}</td>
                    <td>{{ (item.qty * item.vol)|round(3) }}</td>
                    <td>{% if item.expiry %}<span {% if exp_status == 'expired' %}class="expiry-warning"{% elif exp_status == 'expiring_soon' %}class="expiry-warn-soon"{% endif %}>{{ item.expiry }}</span>{% else %}-{% endif %}</td>
                    <td>
                        {% if exp_status == 'expired' %}🔴
                        {% elif exp_status == 'expiring_soon' %}⚠️
                        {% else %}✓
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

<div id="clients" class="tab-content">
    <h2 data-key="clients_title" style="color:var(--accent); font-size: 18px;">👥 Управление клиентами</h2>
    
    <form action="/add_client" method="POST" class="form-row">
        <input name="name" placeholder="Имя клиента" required data-key="f_client_name">
        <input name="phone" placeholder="Телефон" required data-key="f_client_phone">
        <input name="email" placeholder="Email" type="email" data-key="f_client_email">
        <textarea name="address" placeholder="Адрес доставки" data-key="f_client_address"></textarea>
        <button type="submit" class="lang-btn" style="background:var(--accent); color:white; grid-column: span 2; font-size: 12px;">Добавить клиента</button>
    </form>

    <table class="clients-table">
        <thead>
            <tr>
                <th data-key="th_client_name">Имя</th>
                <th data-key="th_client_phone">Телефон</th>
                <th data-key="th_client_email">Email</th>
                <th data-key="th_client_balance">Баланс</th>
                <th data-key="th_client_spent">Потрачено</th>
                <th data-key="th_client_actions">Действия</th>
            </tr>
        </thead>
        <tbody id="clients-list">
            {% for client_id, client in warehouse.clients.items() %}
            <tr>
                <td><b>{{ client.name }}</b></td>
                <td>{{ client.phone }}</td>
                <td>{{ client.email or '-' }}</td>
                <td>{{ "%.2f"|format(client.balance) }} ₽</td>
                <td>{{ "%.2f"|format(client.get('total_spent', 0)) }} ₽</td>
                <td>
                    <button class="action-btn" onclick="addPayment('{{ client_id }}', '{{ client.name }}')">💰</button>
                    <button class="action-btn delete" onclick="deleteClient('{{ client_id }}')">🗑️</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div id="orders" class="tab-content">
    <h2 data-key="orders_title" style="color:var(--accent); font-size: 18px;">📋 Заказы и платежи</h2>
    
    <form id="order-form" action="/add_order" method="POST" class="form-row">
        <select name="client_id" id="order-client" required style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); font-size: 12px;">
            <option value="" data-key="f_select_client">Выберите клиента...</option>
            {% for client_id, client in warehouse.clients.items() %}
            <option value="{{ client_id }}">{{ client.name }}</option>
            {% endfor %}
        </select>
        <input name="order_items" id="order-items" placeholder="Адрес:кол-во (A1:2,B3:5)" data-key="f_order_items" required>
        <div id="item-warning" class="warning-notification" style="grid-column: span 2;"></div>
        <input name="amount" type="number" step="0.01" placeholder="Сумма заказа" id="order-amount" required data-key="f_order_amount" min="0">
        <select name="status" style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); font-size: 12px;">
            <option value="pending">В обработке</option>
            <option value="completed">Завершён</option>
            <option value="returned">Возврат</option>
        </select>
        <button type="submit" class="lang-btn" style="background:var(--accent); color:white; grid-column: span 2; font-size: 12px;">Создать заказ</button>
    </form>

    <table class="orders-table">
        <thead>
            <tr>
                <th data-key="th_order_id">ID</th>
                <th data-key="th_order_client">Клиент</th>
                <th data-key="th_order_amount">Сумма</th>
                <th data-key="th_order_status">Статус</th>
                <th data-key="th_order_paid">Оплачен</th>
                <th data-key="th_order_date">Дата</th>
                <th data-key="th_order_actions">Действия</th>
            </tr>
        </thead>
        <tbody id="orders-list">
            {% for order_id, order in warehouse.orders.items() %}
            {% set client = warehouse.clients.get(order.client_id, {}) %}
            <tr>
                <td><b>{{ order_id[:8] }}</b></td>
                <td>{{ client.get('name', 'N/A') }}</td>
                <td>{{ "%.2f"|format(order.amount) }} ₽</td>
                <td style="font-size: 11px;">
                    {% if order.status == 'pending' %}⏳ Обработка
                    {% elif order.status == 'completed' %}✓ Завершён
                    {% elif order.status == 'returned' %}↩️ Возврат
                    {% endif %}
                </td>
                <td>{% if order.paid %}✓ Да{% else %}❌ Нет{% endif %}</td>
                <td>{{ order.created[:10] }}</td>
                <td>
                    <button class="action-btn" onclick="markPaid('{{ order_id }}')">💳</button>
                    <button class="action-btn delete" onclick="deleteOrder('{{ order_id }}')">🗑️</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
</div>

<div id="modal" class="modal-overlay" onclick="closeModal()">
<div class="modal-content" onclick="event.stopPropagation()">
    <h2 id="m-title" style="color:var(--accent); margin-top:0; font-size: 16px;"></h2>
    <div id="m-info" style="margin-bottom:20px; font-size:13px; line-height:1.6;"></div>
    <form action="/update_item" method="POST">
        <input type="hidden" name="addr" id="m-addr-input">
        <input type="number" name="minus" id="m-minus-input" placeholder="Отгрузить шт." min="0" value="0" style="width:100%; padding:10px; margin-bottom:10px; box-sizing:border-box; font-size: 12px;">
        <button type="submit" class="lang-btn" style="width:100%; background:var(--accent); color:white; font-size: 12px;" data-key="m_apply">Применить</button>
        <button type="button" onclick="fullDelete()" class="lang-btn" style="width:100%; margin-top:5px; background:var(--danger); color:white; font-size: 12px;" data-key="m_clear">Очистить</button>
    </form>
</div>
</div>
{% endif %}

<footer>
<div style="font-weight:bold; font-size:14px; margin-bottom: 10px;">QAQ Team (РФМЛИ)</div>
<div style="display:flex; justify-content:center; gap:40px; flex-wrap:wrap; font-size: 11px;">
    <div><b>Кутаев Магомедрасуслик (ItsJustMp4_)</b> (6 кл.) <br> TG:@ItsJustMp4_<br>HEXAGON❤</div>
    <div><b>Алавов Биймурадик (GER)</b> (8 кл.)<br>TG:GER2548<br>DOTA_2❤</div>
    <div><b>Кунтуганов Ратмирчик (Ambassador of C++)</b> (8 кл.)<br>TG: C_plus_plus_is_good<br>Омнисия❤</div>
</div>
<div style="margin-top:20px; font-size: 11px;"> Техподдержка: +7 928 587 97-74 | +7 964 005 96-16</div>
</footer>

<script>
const i18n = {
    ru: {
        t_title: "QAQ Умный Склад", auth_title: "Вход в систему", auth_login: "Войти", auth_create: "Создать бэкап",
        search_ph: "Поиск товара или ячейки...", f_addr: "Ячейка", f_item: "Товар", f_qty: "Кол-во",
        f_price: "Цена ₽", f_weight: "Вес кг", f_vol: "Объем м³", f_expiry: "Срок годности (необязательно)",
        set_title: "⚙️ Управление лимитами", set_manage_rows: "Управление группами", set_limits_title: "Лимиты групп",
        set_add_row: "Добавить группу", set_save: "Сохранить", set_cells: "Ячеек в ряду:",
        m_apply: "Применить", m_clear: "Очистить", m_minus_ph: "Отгрузить шт.", nav_exit: "Выход", btn_logout: "Выход",
        summary_title: "📊 Смета склада", sum_qty: "Общее количество", sum_weight: "Общий вес",
        sum_volume: "Общий объем", sum_price: "Общая стоимость", items_list_title: "📋 Список товаров",
        sum_expired: "⚠️ Испорчено", sum_expiring: "⏰ Испортится",
        th_addr: "Ячейка", th_item: "Товар", th_qty_table: "Кол-во", th_price_table: "Цена",
        th_weight_table: "Вес (кг)", th_vol_table: "Объем (м³)", th_expiry: "Срок",
        unit_pcs: "шт.", in_stock: "В наличии", price: "Цена", total: "Итого",
        auth_username: "Логин", auth_password: "Пароль",
        error_occupied: "❌ Ячейка занята!", error_not_exist: "❌ Ячейки не существует!",
        error_invalid: "❌ Некорректные данные!", error_user_exists: "❌ Пользователь уже существует!",
        error_user_not_found: "❌ Пользователь не найден!", error_wrong_password: "❌ Неверный пароль!",
        error_invalid_captcha: "❌ Неверный ответ на капчу!", error_overflow: "⚠️ Переполнение ячейки!",
        error_item_not_found: "❌ Товар не найден на складе: ",
        error_insufficient_qty: "❌ Недостаточно товара: ",
        error_invalid_date: "❌ Неверный формат даты!",
        error_invalid_addr: "❌ Неверный формат адреса: ",
        error_invalid_qty: "❌ Неверное количество: ",
        error_invalid_amount: "❌ Неверная сумма!",
        error_invalid_format: "❌ Неверный формат: ",
        error_cell_not_exist: "❌ Ячейка не существует: ",
        error_no_items: "❌ Не указаны товары!",
        error_no_client: "❌ Выберите клиента!",
        error_client_not_found: "❌ Клиент не найден!",
        tab_warehouse: "📦 Склад", tab_clients: "👥 Клиенты", tab_orders: "📋 Заказы",
        clients_title: "👥 Управление клиентами", f_client_name: "Имя клиента", f_client_phone: "Телефон",
        f_client_email: "Email", f_client_address: "Адрес доставки", th_client_name: "Имя",
        th_client_phone: "Телефон", th_client_email: "Email", th_client_balance: "Баланс",
        th_client_spent: "Потрачено", th_client_actions: "Действия", orders_title: "📋 Заказы и платежи",
        f_select_client: "Выберите клиента...", f_order_items: "Адрес:кол-во (A1:2,B3:5)",
        f_order_amount: "Сумма заказа",
        th_order_id: "ID", th_order_client: "Клиент", th_order_amount: "Сумма",
        th_order_status: "Статус", th_order_date: "Дата", th_order_actions: "Действия",
        th_order_paid: "Оплачен",
        item_not_on_warehouse: "⚠️ Товара нет на складе!"
    },
    en: {
        t_title: "QAQ Smart Storage", auth_title: "System Login", auth_login: "Login", auth_create: "Create Backup",
        search_ph: "Search item or cell...", f_addr: "Cell", f_item: "Item", f_qty: "Qty",
        f_price: "Price $", f_weight: "Weight kg", f_vol: "Volume m³", f_expiry: "Expiry Date (optional)",
        set_title: "⚙️ Manage Limits", set_manage_rows: "Manage Groups", set_limits_title: "Group Limits",
        set_add_row: "Add Group", set_save: "Save", set_cells: "Cells per row:",
        m_apply: "Apply", m_clear: "Clear", m_minus_ph: "Dispatch qty", nav_exit: "Logout", btn_logout: "Logout",
        summary_title: "📊 Warehouse Summary", sum_qty: "Total Quantity", sum_weight: "Total Weight",
        sum_volume: "Total Volume", sum_price: "Total Cost", items_list_title: "📋 Items List",
        sum_expired: "⚠️ Expired", sum_expiring: "⏰ Expiring Soon",
        th_addr: "Cell", th_item: "Item", th_qty_table: "Qty", th_price_table: "Price",
        th_weight_table: "Weight (kg)", th_vol_table: "Volume (m³)", th_expiry: "Expiry",
        unit_pcs: "pcs", in_stock: "In stock", price: "Price", total: "Total",
        auth_username: "Username", auth_password: "Password",
        error_occupied: "❌ Cell occupied!", error_not_exist: "❌ Cell does not exist!",
        error_invalid: "❌ Invalid data!", error_user_exists: "❌ User already exists!",
        error_user_not_found: "❌ User not found!", error_wrong_password: "❌ Wrong password!",
        error_invalid_captcha: "❌ Invalid captcha answer!", error_overflow: "⚠️ Cell overflow!",
        error_item_not_found: "❌ Item not found on warehouse: ",
        error_insufficient_qty: "❌ Insufficient quantity: ",
        error_invalid_date: "❌ Invalid date format!",
        error_invalid_addr: "❌ Invalid address format: ",
        error_invalid_qty: "❌ Invalid quantity: ",
        error_invalid_amount: "❌ Invalid amount!",
        error_invalid_format: "❌ Invalid format: ",
        error_cell_not_exist: "❌ Cell does not exist: ",
        error_no_items: "❌ No items specified!",
        error_no_client: "❌ Select a client!",
        error_client_not_found: "❌ Client not found!",
        tab_warehouse: "📦 Warehouse", tab_clients: "👥 Clients", tab_orders: "📋 Orders",
        clients_title: "👥 Manage Clients", f_client_name: "Client Name", f_client_phone: "Phone",
        f_client_email: "Email", f_client_address: "Delivery Address", th_client_name: "Name",
        th_client_phone: "Phone", th_client_email: "Email", th_client_balance: "Balance",
        th_client_spent: "Spent", th_client_actions: "Actions", orders_title: "📋 Orders & Payments",
        f_select_client: "Select Client...", f_order_items: "Address:qty (A1:2,B3:5)",
        f_order_amount: "Order Amount",
        th_order_id: "ID", th_order_client: "Client", th_order_amount: "Amount",
        th_order_status: "Status", th_order_date: "Date", th_order_actions: "Actions",
        th_order_paid: "Paid",
        item_not_on_warehouse: "⚠️ Item not in warehouse!"
    },
    cn: {
        t_title: "QAQ 智能仓库", auth_title: "系统登录", auth_login: "登录", auth_create: "创建备份",
        search_ph: "搜索商品或库位...", f_addr: "库位", f_item: "名称", f_qty: "数量",
        f_price: "价格 ¥", f_weight: "重量 kg", f_vol: "体积 m³", f_expiry: "有效期 (可选)",
        set_title: "⚙️ 管理限制", set_manage_rows: "管理分组", set_limits_title: "分组限制",
        set_add_row: "添加分组", set_save: "保存", set_cells: "每行数量:",
        m_apply: "确定", m_clear: "清空", m_minus_ph: "出库数量", nav_exit: "退出", btn_logout: "退出",
        summary_title: "📊 仓库清单", sum_qty: "总数量", sum_weight: "总重量",
        sum_volume: "总体积", sum_price: "总价格", items_list_title: "📋 商品列表",
        sum_expired: "⚠️ 已过期", sum_expiring: "⏰ 即将过期",
        th_addr: "库位", th_item: "商品", th_qty_table: "数量", th_price_table: "价格",
        th_weight_table: "重量 (kg)", th_vol_table: "体积 (m³)", th_expiry: "期限",
        unit_pcs: "件", in_stock: "库存", price: "价格", total: "小计",
        auth_username: "用户名", auth_password: "密码",
        error_occupied: "❌ 库位已占用!", error_not_exist: "❌ 库位不存在!",
        error_invalid: "❌ 数据无效!", error_user_exists: "❌ 用户已存在!",
        error_user_not_found: "❌ 用户未找到!", error_wrong_password: "❌ 密码错误!",
        error_invalid_captcha: "❌ 验证码错误!", error_overflow: "⚠️ 库位满载!",
        error_item_not_found: "❌ 仓库中未找到商品: ",
        error_insufficient_qty: "❌ 数量不足: ",
        error_invalid_date: "❌ 日期格式无效!",
        error_invalid_addr: "❌ 库位格式无效: ",
        error_invalid_qty: "❌ 数量无效: ",
        error_invalid_amount: "❌ 金额无效!",
        error_invalid_format: "❌ 格式无效: ",
        error_cell_not_exist: "❌ 库位不存在: ",
        error_no_items: "❌ 未指定商品!",
        error_no_client: "❌ 选择客户!",
        error_client_not_found: "❌ 客户未找到!",
        tab_warehouse: "📦 仓库", tab_clients: "👥 客户", tab_orders: "📋 订单",
        clients_title: "👥 管理客户", f_client_name: "客户名称", f_client_phone: "电话",
        f_client_email: "邮箱", f_client_address: "配送地址", th_client_name: "名称",
        th_client_phone: "电话", th_client_email: "邮箱", th_client_balance: "余额",
        th_client_spent: "消费", th_client_actions: "操作", orders_title: "📋 订单和付款",
        f_select_client: "选择客户...", f_order_items: "库位:数量 (A1:2,B3:5)",
        f_order_amount: "订单金额",
        th_order_id: "ID", th_order_client: "客户", th_order_amount: "金额",
        th_order_status: "状态", th_order_date: "日期", th_order_actions: "操作",
        th_order_paid: "已付",
        item_not_on_warehouse: "⚠️ 仓库中无此商品!"
    }
};

const cellsData = {{ warehouse.cells|tojson if warehouse else '{}' }};
let activeGroups = {{ warehouse.rows|tojson if warehouse else '[]' }};
let rowConfigs = {{ warehouse.row_configs|tojson if warehouse else '{}' }};
let currentLang = localStorage.getItem('lang') || 'ru';

function setLang(lang) {
    localStorage.setItem('lang', lang);
    currentLang = lang;
    const d = i18n[lang];
    
    document.querySelectorAll('.lang-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`lang-${lang}`).classList.add('active');
    
    document.querySelectorAll('[data-key]').forEach(el => {
        const k = el.getAttribute('data-key');
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = d[k];
        else if (el.tagName === 'OPTION') el.innerText = d[k];
        else el.innerText = d[k];
    });
    
    const authUsername = document.getElementById('auth-username');
    const authPassword = document.getElementById('auth-password');
    if(authUsername) authUsername.placeholder = d.auth_username;
    if(authPassword) authPassword.placeholder = d.auth_password;
    
    document.querySelectorAll('.unit-label').forEach(el => {
        el.innerText = d.unit_pcs;
    });
    if(document.getElementById('unit-qty'))
        document.getElementById('unit-qty').innerText = d.unit_pcs;
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
}

function doSearch() {
    const q = document.getElementById('search').value.toUpperCase();
    const dropdown = document.getElementById('search-dropdown');
    if(!q) { dropdown.style.display = 'none'; return; }
    
    let html = '';
    for(let addr in cellsData) {
        const item = cellsData[addr];
        if(item && (item.name.toUpperCase().includes(q) || addr.includes(q))) {
            html += `<div class="search-item" onclick="openInspector('${addr}', '${item.name}', ${item.qty}, ${item.price}, '${item.expiry || ''}')">
                <b>${addr}</b> - ${item.name} (${item.qty} ${i18n[currentLang].unit_pcs})<br>
                <small>₽${item.price} | ${item.weight}kg | ${item.vol}m³ | ${item.expiry || 'без сроков'}</small>
            </div>`;
        }
    }
    dropdown.innerHTML = html || '<div class="search-item">Not found</div>';
    dropdown.style.display = 'block';
}

function toggleSettings() {
    const p = document.getElementById('settings-panel');
    p.style.display = p.style.display === 'block' ? 'none' : 'block';
    if(p.style.display === 'block') renderGroupsUI();
}

function syncActiveGroupsFromDOM() {
    const container = document.getElementById('groups-container');
    activeGroups = Array.from(container.querySelectorAll('.group-row')).map(row => row.dataset.group);
}

function attachGroupDnD(container) {
    let draggedRow = null;

    const rows = container.querySelectorAll('.group-row');
    rows.forEach(row => {
        row.addEventListener('dragstart', (e) => {
            draggedRow = row;
            row.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        row.addEventListener('dragend', () => {
            row.classList.remove('dragging');
            container.querySelectorAll('.group-row').forEach(r => r.classList.remove('drag-over'));
            draggedRow = null;
            syncActiveGroupsFromDOM();
        });

        row.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!draggedRow || draggedRow === row) return;
            const rect = row.getBoundingClientRect();
            const after = (e.clientY - rect.top) > (rect.height / 2);
            container.querySelectorAll('.group-row').forEach(r => r.classList.remove('drag-over'));
            row.classList.add('drag-over');
            if (after) {
                row.after(draggedRow);
            } else {
                row.before(draggedRow);
            }
        });

        row.addEventListener('drop', (e) => {
            e.preventDefault();
            syncActiveGroupsFromDOM();
        });
    });
}

function renderGroupsUI() {
    const container = document.getElementById('groups-container');
    container.innerHTML = '';
    activeGroups.forEach(group => {
        const numCells = rowConfigs[group]?.num_cells || 10;
        const row = document.createElement('div');
        row.className = 'group-row';
        row.draggable = true;
        row.dataset.group = group;
        row.innerHTML = `
            <span class="drag-handle" title="Перетащить">⋮⋮</span>
            <input type="hidden" name="group_name[]" value="${group}">
            <span style="font-weight:bold; text-align:center; font-size: 12px;">${group}</span>
            <input type="number" name="group_cells[]" value="${numCells}" min="1" max="20" style="padding:6px; border-radius:6px; border:1px solid var(--border); background:var(--bg-input); color:var(--text-main); font-size: 12px;">
            <button type="button" class="btn-remove" onclick="removeGroup('${group}')" style="font-size: 11px;">Удалить</button>
        `;
        container.appendChild(row);
    });
    attachGroupDnD(container);
    syncActiveGroupsFromDOM();
}

function addNewGroup() {
    const allRows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O'];
    const available = allRows.filter(r => !activeGroups.includes(r));
    if(available.length === 0) { alert('Все группы добавлены!'); return; }
    const newGroup = available[0];
    activeGroups.push(newGroup);
    if(!rowConfigs[newGroup]) rowConfigs[newGroup] = {num_cells: 10};
    renderGroupsUI();
}

function removeGroup(group) {
    if(confirm(`Удалить группу ${group}?`)) {
        activeGroups = activeGroups.filter(r => r !== group);
        renderGroupsUI();
    }
}

function setCell(a) {
    document.getElementById('p-addr').value = a;
    switchTab('warehouse');
    setTimeout(() => {
        document.getElementById('p-addr').focus();
    }, 100);
}

function openInspector(addr, name, qty, price, expiry) {
    const d = i18n[currentLang];
    document.getElementById('m-title').innerText = addr + " | " + name;
    let expiryText = expiry ? ` | ${d.th_expiry}: ${expiry}` : '';
    document.getElementById('m-info').innerHTML =
        `<b>${d.in_stock}:</b> ${qty} ${d.unit_pcs}<br><b>${d.price}:</b> ${price} ₽${expiryText}<br><b>${d.total}:</b> ${(qty*price).toFixed(2)} ₽`;
    document.getElementById('m-addr-input').value = addr;
    document.getElementById('m-minus-input').value = '0';
    document.getElementById('modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('modal').style.display = 'none';
}

function fullDelete() {
    const a = document.getElementById('m-addr-input').value;
    if(confirm("Очистить " + a + "?")) window.location.href="/delete/"+a;
}

function toggleTheme() {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

function validateOrderItems() {
    const itemsStr = document.getElementById('order-items').value.trim();
    const warning = document.getElementById('item-warning');
    warning.classList.remove('show');
    warning.innerHTML = '';
    
    if(!itemsStr) return true;
    
    const items = itemsStr.split(',');
    for(let item of items) {
        item = item.trim();
        if(!item) continue;
        if(!item.includes(':')) {
            showItemWarning('❌ Формат: адрес:количество (A1:2)');
            return false;
        }
        
        const [addr, qty] = item.split(':');
        const addrUpper = addr.toUpperCase().trim();
        
        if(!cellsData[addrUpper]) {
            showItemWarning(`⚠️ ${i18n[currentLang].error_item_not_found} ${addrUpper}`);
            return false;
        }
        
        const available = cellsData[addrUpper].qty;
        const requested = parseInt(qty) || 0;
        if(requested > available) {
            showItemWarning(`⚠️ ${i18n[currentLang].error_insufficient_qty}${addrUpper} (нужно: ${requested}, есть: ${available})`);
            return false;
        }
    }
    return true;
}

function showItemWarning(msg) {
    const warning = document.getElementById('item-warning');
    warning.innerHTML = msg;
    warning.classList.add('show');
}

if(document.getElementById('order-items')) {
    document.getElementById('order-items').addEventListener('input', validateOrderItems);
    document.getElementById('order-items').addEventListener('blur', validateOrderItems);
}

function addPayment(clientId, clientName) {
    const amount = prompt(`${i18n[currentLang].th_client_balance} для ${clientName}:`);
    if(amount && !isNaN(parseFloat(amount)) && parseFloat(amount) > 0) {
        window.location.href = `/add_payment/${clientId}/${parseFloat(amount)}`;
    } else if(amount !== null) {
        alert('Некорректная сумма!');
    }
}

function deleteClient(clientId) {
    if(confirm('Удалить этого клиента и все его заказы?')) {
        window.location.href = `/delete_client/${clientId}`;
    }
}

function markPaid(orderId) {
    if(confirm('Отметить заказ как оплаченный?')) {
        window.location.href = `/mark_paid/${orderId}`;
    }
}

function deleteOrder(orderId) {
    if(confirm('Удалить заказ?')) {
        window.location.href = `/delete_order/${orderId}`;
    }
}

function initApp() {
    setLang(localStorage.getItem('lang') || 'ru');
    if(localStorage.getItem('theme') === 'dark') document.body.setAttribute('data-theme', 'dark');
}
</script>

</body>
</html>
"""
# ===== ЧАСТЬ 7: FLASK МАРШРУТЫ (часть 1/4) =====

@app.route('/')
def index():
    wh = get_wh()
    if not wh:
        a, b = random.randint(1,10), random.randint(1,10)
        session['captcha_res'] = a+b
        return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}")
    today = datetime.now().strftime('%Y-%m-%d')
    error_msg = session.pop('last_error', wh.last_error if wh else "")
    return render_template_string(HTML_TEMPLATE, warehouse=wh, row_stats=wh.get_row_stats(),
                                total_stats=wh.get_total_stats(), error=error_msg, draft=wh.draft, today=today)

@app.route('/auth', methods=['POST'])
def auth():
    u = request.form.get('username', '').strip()
    p = request.form.get('password', '')
    action = request.form.get('action', '')
    captcha = request.form.get('captcha', '')
    
    try:
        captcha_answer = int(captcha or 0)
    except ValueError:
        captcha_answer = -1
    
    if captcha_answer != session.get('captcha_res'):
        a, b = random.randint(1,10), random.randint(1,10)
        session['captcha_res'] = a+b
        return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Неверный ответ на капчу!", last_username=u)
    
    if not u or len(u) < 3 or not p or len(p) < 3:
        a, b = random.randint(1,10), random.randint(1,10)
        session['captcha_res'] = a+b
        return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Логин и пароль должны быть минимум 3 символа!", last_username=u)
    
    if len(u) > 50 or len(p) > 100:
        a, b = random.randint(1,10), random.randint(1,10)
        session['captcha_res'] = a+b
        return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Данные слишком длинные!", last_username=u)
    
    users = load_users()
    
    if action == 'register':
        if u in users:
            a, b = random.randint(1,10), random.randint(1,10)
            session['captcha_res'] = a+b
            return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Пользователь уже существует!", last_username=u)
        
        try:
            users[u] = generate_password_hash(p)
            save_users(users)
            session['user'] = u
            SmartWarehouse(u).save_to_backup()
            return redirect('/')
        except Exception as e:
            a, b = random.randint(1,10), random.randint(1,10)
            session['captcha_res'] = a+b
            return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Ошибка регистрации!", last_username=u)
    
    elif action == 'login':
        if u not in users:
            a, b = random.randint(1,10), random.randint(1,10)
            session['captcha_res'] = a+b
            return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Пользователь не найден!", last_username=u)
        
        try:
            if check_password_hash(users[u], p):
                session['user'] = u
                return redirect('/')
            else:
                a, b = random.randint(1,10), random.randint(1,10)
                session['captcha_res'] = a+b
                return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Неверный пароль!", last_username=u)
        except Exception as e:
            a, b = random.randint(1,10), random.randint(1,10)
            session['captcha_res'] = a+b
            return render_template_string(HTML_TEMPLATE, captcha_q=f"{a}+{b}", auth_error="❌ Ошибка входа!", last_username=u)
    
    return redirect('/')
# ===== ЧАСТЬ 8: FLASK МАРШРУТЫ (часть 2/4) =====

@app.route('/add', methods=['POST'])
def add():
    wh = get_wh()
    if wh:
        try:
            addr = request.form.get('addr', '').strip()
            name = request.form.get('name', '').strip()
            qty = request.form.get('qty', '0')
            price = request.form.get('price', '0')
            weight = request.form.get('weight', '0')
            vol = request.form.get('vol', '0')
            expiry = request.form.get('expiry', '').strip()
            
            if not addr or not name:
                session['last_error'] = "ERROR_INVALID_DATA"
            else:
                if not wh.add_item(addr, name, qty, price, weight, vol, expiry):
                    session['last_error'] = wh.last_error
        except Exception as e:
            session['last_error'] = "ERROR_INVALID_DATA"
    return redirect('/')

@app.route('/update_item', methods=['POST'])
def update_item():
    wh = get_wh()
    if wh:
        try:
            addr = request.form.get('addr', '').strip().upper()
            minus = request.form.get('minus', '0').strip()
            
            if not addr or addr not in wh.cells:
                return redirect('/')
            
            try:
                m = int(minus) if minus else 0
            except ValueError:
                m = 0
            
            m = max(0, m)
            
            if wh.cells[addr]:
                current_qty = wh.cells[addr]['qty']
                if m > current_qty:
                    m = current_qty
                if m > 0:
                    wh.cells[addr]['qty'] -= m
                    if wh.cells[addr]['qty'] <= 0:
                        wh.cells[addr] = None
                    wh.save_to_backup()
        except (ValueError, TypeError, KeyError):
            pass
    return redirect('/')

@app.route('/delete/<addr>')
def delete(addr):
    wh = get_wh()
    if wh:
        try:
            addr = addr.upper().strip()
            if addr in wh.cells:
                wh.cells[addr] = None
                wh.save_to_backup()
        except Exception:
            pass
    return redirect('/')

@app.route('/add_client', methods=['POST'])
def add_client():
    wh = get_wh()
    if wh:
        try:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            address = request.form.get('address', '').strip()
            
            if not name or not phone:
                session['last_error'] = "ERROR_INVALID_DATA"
                return redirect('/')
            
            if len(name) > 100 or len(phone) > 50 or len(email) > 100 or len(address) > 300:
                session['last_error'] = "ERROR_INVALID_DATA"
                return redirect('/')
            
            if not wh.add_client(name, phone, email, address):
                session['last_error'] = wh.last_error
        except Exception:
            session['last_error'] = "ERROR_INVALID_DATA"
    return redirect('/')
# ===== ЧАСТЬ 9: FLASK МАРШРУТЫ (часть 3/4) =====

@app.route('/delete_client/<client_id>')
def delete_client(client_id):
    wh = get_wh()
    if wh:
        try:
            client_id = client_id.strip()
            if client_id in wh.clients:
                for order_id in wh.clients[client_id].get('orders', []):
                    if order_id in wh.orders:
                        del wh.orders[order_id]
                
                del wh.clients[client_id]
                wh.save_clients_data()
                wh.save_orders_data()
        except Exception:
            pass
    return redirect('/')

@app.route('/add_payment/<client_id>/<amount>')
def add_payment(client_id, amount):
    wh = get_wh()
    if wh:
        try:
            client_id = client_id.strip()
            amount_float = float(amount)
            
            if amount_float < 0:
                return redirect('/')
            
            if client_id in wh.clients:
                wh.clients[client_id]['balance'] += amount_float
                wh.save_clients_data()
        except (ValueError, TypeError):
            pass
    return redirect('/')

@app.route('/add_order', methods=['POST'])
def add_order():
    wh = get_wh()
    if wh:
        try:
            client_id = request.form.get('client_id', '').strip()
            items = request.form.get('order_items', '').strip()
            amount = request.form.get('amount', '0').strip()
            status = request.form.get('status', 'pending').strip()
            
            if status not in ['pending', 'completed', 'returned']:
                status = 'pending'
            
            if not client_id:
                session['last_error'] = "ERROR_NO_CLIENT"
                return redirect('/')
            
            if not items:
                session['last_error'] = "ERROR_NO_ITEMS"
                return redirect('/')
            
            try:
                amount_float = float(amount)
                if amount_float <= 0:
                    session['last_error'] = "ERROR_INVALID_AMOUNT"
                    return redirect('/')
            except ValueError:
                session['last_error'] = "ERROR_INVALID_AMOUNT"
                return redirect('/')
            
            if not wh.add_order(client_id, items, amount_float, status):
                session['last_error'] = wh.last_error
            
        except Exception as e:
            session['last_error'] = f"ERROR_UNKNOWN"
    
    return redirect('/')

@app.route('/delete_order/<order_id>')
def delete_order(order_id):
    wh = get_wh()
    if wh:
        try:
            order_id = order_id.strip()
            if order_id in wh.orders:
                client_id = wh.orders[order_id]['client_id']
                del wh.orders[order_id]
                
                if client_id in wh.clients:
                    wh.clients[client_id]['orders'] = [o for o in wh.clients[client_id]['orders'] if o != order_id]
                
                wh.save_orders_data()
                wh.save_clients_data()
        except Exception:
            pass
    return redirect('/')

@app.route('/mark_paid/<order_id>')
def mark_paid(order_id):
    wh = get_wh()
    if wh:
        try:
            order_id = order_id.strip()
            if order_id in wh.orders:
                order = wh.orders[order_id]
                if not order.get('paid', False):
                    for addr, qty in order.get('items', {}).items():
                        if addr in wh.cells and wh.cells[addr]:
                            try:
                                need = int(qty)
                            except (TypeError, ValueError):
                                need = 0
                            if need > 0:
                                current_qty = wh.cells[addr].get('qty', 0)
                                wh.cells[addr]['qty'] = max(0, current_qty - need)
                                if wh.cells[addr]['qty'] == 0:
                                    wh.cells[addr] = None
                    order['paid'] = True
                    order['status'] = 'completed'
                    wh.save_orders_data()
                    wh.save_to_backup()
        except Exception:
            pass
    return redirect('/')
# ===== ЧАСТЬ 10: FLASK МАРШРУТЫ (часть 4/4) И ЗАПУСК =====

@app.route('/update_groups', methods=['POST'])
def update_groups():
    wh = get_wh()
    if wh:
        try:
            keys = request.form.getlist('row_key[]')
            ws = request.form.getlist('row_w[]')
            vs = request.form.getlist('row_v[]')
            
            if keys and ws and vs and len(keys) == len(ws) == len(vs):
                try:
                    new_limits = {}
                    for k, w, v in zip(keys, ws, vs):
                        try:
                            w_val = float(w)
                            v_val = float(v)
                            if w_val > 0 and v_val > 0:
                                new_limits[k] = {'w': w_val, 'v': v_val}
                            else:
                                new_limits[k] = DEFAULT_LIMITS.get(k, {'w': 500, 'v': 2})
                        except ValueError:
                            new_limits[k] = DEFAULT_LIMITS.get(k, {'w': 500, 'v': 2})
                    
                    wh.rows_limits = new_limits
                except Exception:
                    wh.rows_limits = DEFAULT_LIMITS.copy()
            
            group_names = request.form.getlist('group_name[]')
            group_cells = request.form.getlist('group_cells[]')
            
            if group_names and group_cells and len(group_names) == len(group_cells):
                wh.rows = group_names
                new_configs = {}
                
                for name, cells in zip(group_names, group_cells):
                    try:
                        cell_count = int(cells)
                        if 1 <= cell_count <= 50:
                            new_configs[name] = {'num_cells': cell_count}
                        else:
                            new_configs[name] = {'num_cells': 10}
                    except (ValueError, TypeError):
                        new_configs[name] = {'num_cells': 10}
                
                wh.row_configs = new_configs
            
            wh._init_cells()
            wh.save_to_backup()
        except Exception as e:
            pass
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(port=5001, debug=True)