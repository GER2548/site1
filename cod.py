# ===== ЧАСТЬ 1: ИМПОРТЫ И КОНФИГУРАЦИЯ =====

import json
import os
import random
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_qaq_key"
USERS_FILE = "users.json"
HISTORY_FILE_TEMPLATE = "history_{}.json"

# --- ДЕФОЛТНЫЕ ЛИМИТЫ ---
DEFAULT_LIMITS = {
    'A': {'w': 500, 'v': 2}, 'B': {'w': 600, 'v': 3}, 'C': {'w': 750, 'v': 5},
    'D': {'w': 950, 'v': 8}, 'E': {'w': 1200, 'v': 13}, 'F': {'w': 1700, 'v': 21},
    'G': {'w': 2700, 'v': 34}, 'H': {'w': 4200, 'v': 55}, 'I': {'w': 6200, 'v': 89}, 'J': {'w': 8700, 'v': 144}
}

# --- КУРСЫ ВАЛЮТ (кэш) ---
CURRENCY_RATES = {
    'RUB': 1.0,
    'USD': 0.011,
    'EUR': 0.010,
    'CNY': 0.077
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

def load_history(username):
    hist_file = HISTORY_FILE_TEMPLATE.format(username)
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"sales": [], "purchases": [], "supplies": [], "transactions": []}

def save_history(username, history):
    hist_file = HISTORY_FILE_TEMPLATE.format(username)
    try:
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
    except:
        pass

def add_history_entry(username, entry_type, data):
    """Добавить запись в историю (sales/purchases/supplies/transactions)"""
    history = load_history(username)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "data": data
    }
    if entry_type in history:
        history[entry_type].append(entry)
        save_history(username, history)

# ===== ЧАСТЬ 3: КЛАСС SmartWarehouse (часть 1/4) =====

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
        self.last_error_field = ""
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
        """Инициализация ячеек с защитой от ошибок"""
        for r in self.rows:
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
            "rows": self.rows
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
                    self.rows = data.get("rows", ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'])
                    self.rows_limits = data.get("limits", DEFAULT_LIMITS.copy())
                    self.row_configs = data.get("row_configs", {r: {'num_cells': 10} for r in self.rows})
            except:
                pass

    # ===== ЧАСТЬ 4: КЛАСС SmartWarehouse (часть 2/4) =====

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
        self.last_error_field = ""
        addr = addr.upper().strip()
        
        try:
            q = int(qty)
            p = float(price)
            w = float(weight)
            v = float(vol)
        except (ValueError, TypeError):
            self.last_error = "ERROR_INVALID_DATA"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        
        if not addr or not name or q <= 0 or p < 0 or w < 0 or v < 0:
            self.last_error = "ERROR_INVALID_DATA"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        
        if len(addr) < 2:
            self.last_error = "ERROR_INVALID_ADDR"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        
        if expiry:
            try:
                datetime.strptime(expiry, '%Y-%m-%d')
            except ValueError:
                self.last_error = "ERROR_INVALID_DATE"
                self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
                return False
        
        if addr not in self.cells:
            self.last_error = "ERROR_NOT_EXIST"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        if self.cells[addr]:
            self.last_error = "ERROR_OCCUPIED"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        
        lim = self.rows_limits.get(addr[0], DEFAULT_LIMITS.get(addr[0], {'w': 500, 'v': 2}))
        
        if (q * w) > lim['w']:
            self.last_error = f"OVERFLOW_WEIGHT|{q}|{addr[0]}"
            self.last_error_field = "weight"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
            return False
        
        if (q * v) > lim['v']:
            self.last_error = f"OVERFLOW_VOLUME|{q}|{addr[0]}"
            self.last_error_field = "volume"
            self.draft = {"addr": addr, "name": name, "qty": qty, "price": price, "weight": weight, "vol": vol, "expiry": expiry}
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
        add_history_entry(self.username, "supplies", {
            "addr": addr,
            "name": name,
            "qty": q,
            "price": p
        })
        self.draft = {k: "" for k in self.draft}
        return True

    def update_item(self, addr, qty=None, name=None, price=None, weight=None, vol=None, expiry=None):
        """Обновить параметры товара"""
        addr = addr.upper().strip()
        if addr not in self.cells or not self.cells[addr]:
            self.last_error = "ERROR_ITEM_NOT_FOUND"
            return False
        
        try:
            item = self.cells[addr]
            if qty is not None:
                item['qty'] = max(0, int(qty))
            if name is not None:
                item['name'] = name.strip()
            if price is not None:
                item['price'] = max(0, float(price))
            if weight is not None:
                item['weight'] = max(0, float(weight))
            if vol is not None:
                item['vol'] = max(0, float(vol))
            if expiry is not None:
                item['expiry'] = expiry if expiry else None
            
            self.save_to_backup()
            return True
        except (ValueError, TypeError):
            self.last_error = "ERROR_INVALID_DATA"
            return False

    # ===== ЧАСТЬ 5: КЛАСС SmartWarehouse (часть 3/4) =====

    def add_order(self, client_id, order_items_dict, amount, status="pending"):
        """Добавить заказ с уже распарсенными items (словарь)"""
        try:
            if client_id not in self.clients:
                self.last_error = "ERROR_CLIENT_NOT_FOUND"
                return False
            
            if not order_items_dict or len(order_items_dict) == 0:
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
            
            # Валидация товаров перед добавлением
            for addr, qty in order_items_dict.items():
                if addr not in self.cells:
                    self.last_error = f"ERROR_CELL_NOT_EXIST|{addr}"
                    return False
                
                if self.cells[addr] is None:
                    self.last_error = f"ERROR_ITEM_NOT_FOUND|{addr}"
                    return False
                
                item_data = self.cells[addr]
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    self.last_error = f"ERROR_INVALID_QTY|{addr}|{qty}"
                    return False
                
                if qty_int <= 0:
                    self.last_error = f"ERROR_INVALID_QTY|{addr}|{qty_int}"
                    return False
                
                if item_data['qty'] < qty_int:
                    self.last_error = f"ERROR_INSUFFICIENT_QTY|{addr}|{qty_int}|{item_data['qty']}"
                    return False
                
            # --- ВСТАВИТЬ ЭТОТ БЛОК ---
            # Списание товаров из ячеек
            for addr, qty in order_items_dict.items():
                qty_int = int(qty)
                self.cells[addr]['qty'] -= qty_int
                # Если в ячейке стало 0, можно либо оставить пустой словарь, либо очистить (None)
                if self.cells[addr]['qty'] <= 0:
                    self.cells[addr] = None
            
            self.save_to_backup() # Сохраняем обновленное состояние склада
            # ---------------------------
            
            order_id = str(int(datetime.now().timestamp() * 1000))
            self.orders[order_id] = {
                "client_id": client_id,
                "items": order_items_dict,
                "amount": amount_float,
                "status": status,
                "created": datetime.now().isoformat(),
                "paid": False
            }
            self.clients[client_id]["orders"].append(order_id)
            self.clients[client_id]["total_spent"] += amount_float
            
            self.save_orders_data()
            self.save_clients_data()
            add_history_entry(self.username, "sales", {
                "client": self.clients[client_id]["name"],
                "items": order_items_dict,
                "amount": amount_float
            })
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

    # ===== ЧАСТЬ 6: КЛАСС SmartWarehouse (часть 4/4) =====

    def get_statistics(self):
        """Получить статистику для графиков"""
        history = load_history(self.username)
        
        sales_by_day = {}
        purchases_by_day = {}
        supplies_by_day = {}
        
        for entry in history.get("sales", []):
            day = entry["timestamp"][:10]
            sales_by_day[day] = sales_by_day.get(day, 0) + entry["data"].get("amount", 0)
        
        for entry in history.get("purchases", []):
            day = entry["timestamp"][:10]
            purchases_by_day[day] = purchases_by_day.get(day, 0) + entry["data"].get("amount", 0)
        
        for entry in history.get("supplies", []):
            day = entry["timestamp"][:10]
            supplies_by_day[day] = supplies_by_day.get(day, 0) + entry["data"].get("qty", 0)
        
        return {
            "sales": sales_by_day,
            "purchases": purchases_by_day,
            "supplies": supplies_by_day
        }

def get_wh():
    if 'user' in session: return SmartWarehouse(session['user'])
    return None
# ===== ЧАСТЬ 7: HTML TEMPLATE (начало) =====

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>QAQ Smart Storage</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <style>
        :root {
            --bg-page: #F0F8FF; --bg-card: #ffffff; --bg-input: #f9f9f9;
            --text-main: #333333; --accent: #00BFFF; --cell-empty: #E1F5FE; --border: #ddd;
            --danger: #ff4757; --footer-text: #87CEEB; --warning: #ffa502; --success: #2ed573;
        }
        [data-theme="dark"] {
            --bg-page: #121212; --bg-card: #1e1e1e; --bg-input: #2d2d2d;
            --text-main: #e0e0e0; --accent: #9575cd; --cell-empty: #333333; --border: #444;
            --footer-text: #9575cd; --warning: #ff9800; --success: #1abc9c;
        }
        body { font-family: 'Segoe UI', sans-serif; background: var(--bg-page); color: var(--text-main); margin: 0; padding: 20px; transition: 0.3s; }
        .container { max-width: 1400px; width: 100%; margin: 0 auto; background: var(--bg-card); padding: 30px; border-radius: 24px; box-shadow: 0 15px 50px rgba(0,0,0,0.1); box-sizing: border-box; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; max-width: 1400px; margin-inline: auto; flex-wrap: wrap; gap: 10px; }
        .lang-btn { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main); padding: 8px 15px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.3s; }
        .lang-btn.active { background: var(--accent); color: white; }
        .lang-btn:hover { background: var(--bg-input); }
        
        .header-section { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 30px; }
        .search-wrapper { position: relative; width: 350px; }
        .search-box { padding: 12px; border: 2px solid var(--accent); border-radius: 10px; width: 100%; background: var(--bg-input); color: var(--text-main); outline: none; box-sizing: border-box; }
        .search-dropdown { position: absolute; top: 110%; left: 0; width: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); max-height: 400px; overflow-y: auto; display: none; z-index: 100; }
        .search-item { padding: 12px; border-bottom: 1px solid var(--border); cursor: pointer; font-size: 12px; }
        .search-item:hover { background: var(--bg-input); }

        .tabs { display: flex; gap: 10px; margin-bottom: 30px; border-bottom: 2px solid var(--border); flex-wrap: wrap; overflow-x: auto; }
        .tab-btn { background: none; border: none; color: var(--text-main); padding: 12px 20px; cursor: pointer; font-weight: bold; border-bottom: 3px solid transparent; transition: all 0.3s; font-size: 14px; white-space: nowrap; }
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

        .settings-panel { display: none; background: var(--bg-input); padding: 20px; border-radius: 16px; margin-bottom: 20px; border: 2px dashed var(--accent); max-height: 600px; overflow-y: auto; }
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

        .error-notification { background: rgba(255, 71, 87, 0.1); border: 2px solid var(--danger); color: var(--danger); padding: 15px; border-radius: 12px; margin-bottom: 20px; display: none; font-size: 13px; font-weight: bold; position: sticky; top: 0; z-index: 999; }
        .error-notification.show { display: block; animation: slideDown 0.3s ease; }
        .warning-notification { background: rgba(255, 165, 2, 0.1); border: 2px solid var(--warning); color: var(--warning); padding: 12px; border-radius: 8px; margin-bottom: 15px; display: none; font-size: 12px; }
        .warning-notification.show { display: block; }
        @keyframes slideDown { from { transform: translateY(-20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(3px); overflow-y: auto; }
        .modal-content { background: var(--bg-card); padding: 30px; border-radius: 20px; width: 500px; border: 2px solid var(--accent); max-height: 90vh; overflow-y: auto; box-sizing: border-box; margin: 20px auto; }

        .modal-buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 15px; }
        .modal-btn { padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.3s; }
        .modal-btn.primary { background: var(--accent); color: white; }
        .modal-btn.primary:hover { opacity: 0.8; }
        .modal-btn.danger { background: var(--danger); color: white; }
        .modal-btn.danger:hover { opacity: 0.8; }
        .modal-btn.success { background: var(--success); color: white; }
        .modal-btn.success:hover { opacity: 0.8; }

        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--bg-input); padding: 20px; border-radius: 16px; border: 2px solid var(--accent); }
        .stat-card h3 { margin-top: 0; color: var(--accent); }
        .stat-card canvas { max-height: 300px; }

        .history-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 20px; }
        .history-list { max-height: 600px; overflow-y: auto; }
        .history-item { background: var(--bg-input); padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid var(--accent); }
        .history-item.supply { border-left-color: #2ed573; }
        .history-item.sale { border-left-color: #00bfff; }
        .history-item.purchase { border-left-color: #ff9800; }
        .history-item.transaction { border-left-color: #9575cd; }
        .history-time { font-size: 11px; color: #999; }
        .history-data { font-size: 12px; margin-top: 5px; }

        footer { margin-top: 50px; padding: 30px; text-align: center; color: var(--footer-text); border-top: 1px solid var(--border); font-size: 11px; }

        .user-info { display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
        .username-display { font-weight: bold; color: var(--text-main); font-size: 14px; }
        .logout-btn { background: var(--danger); color: white; padding: 8px 15px; border-radius: 8px; text-decoration: none; cursor: pointer; border: none; font-weight: bold; font-size: 13px; }
        .logout-btn:hover { opacity: 0.8; }

        .currency-selector { display: flex; gap: 10px; margin-bottom: 20px; }
        .currency-btn { padding: 8px 15px; border: 2px solid var(--border); background: var(--bg-card); color: var(--text-main); border-radius: 8px; cursor: pointer; font-weight: bold; }
        .currency-btn.active { border-color: var(--accent); background: var(--accent); color: white; }

        .auth-error { background: rgba(255, 71, 87, 0.15); border: 2px solid var(--danger); color: var(--danger); padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center; font-weight: bold; font-size: 12px; }

        .action-btn { background: var(--accent); color: white; border: none; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 11px; margin-right: 3px; transition: 0.3s; }
        .action-btn:hover { opacity: 0.8; }
        .action-btn.delete { background: var(--danger); }
        .action-btn.success { background: var(--success); }

        .order-item-display { background: var(--bg-input); padding: 10px; border-radius: 8px; margin: 5px 0; border-left: 4px solid var(--accent); }
        .order-item-display .addr { font-weight: bold; color: var(--accent); }
        .order-item-display .qty { color: var(--text-main); }
        .order-item-display .price { color: var(--success); font-weight: bold; }

        .status-badge { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold; }
        .status-pending { background: rgba(255, 165, 2, 0.2); color: #ff9800; }
        .status-completed { background: rgba(46, 213, 115, 0.2); color: #2ed573; }
        .status-returned { background: rgba(255, 71, 87, 0.2); color: #ff4757; }
    </style>
</head>
<body onload="initApp()">

<div class="top-nav">
    <div>
        <button class="lang-btn" id="lang-ru" onclick="setLang('ru')">🇷🇺 RU</button>
        <button class="lang-btn" id="lang-en" onclick="setLang('en')">🇬🇧 EN</button>
        <button class="lang-btn" id="lang-cn" onclick="setLang('cn')">🇨🇳 CN</button>
    </div>
    <div class="currency-selector" id="currency-selector"></div>
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
        <button type="submit" name="action" value="register" class="lang-btn" style="width:100%; margin-top:10px; background:#666; color:white;" data-key="auth_create">Создать аккаунт</button>
    </form>
</div>
{% else %}
<div class="container">

    <div id="error-notification" class="error-notification"></div>

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
                <tr><th style="font-size: 12px;">Ряд</th><th style="font-size: 12px;" data-key="th_weight_table">Вес (кг)</th><th style="font-size: 12px;" data-key="th_vol_table">Объем (м³)</th></tr>
                {% for r in warehouse.rows %}
                <tr>
                    <td><b>{{ r }}</b><input type="hidden" name="row_key[]" value="{{ r }}"></td>
                    <td><input type="number" name="row_w[]" value="{{ warehouse.rows_limits.get(r, {}).get('w', 500) }}" style="width:70px; padding: 6px;"></td>
                    <td><input type="number" name="row_v[]" value="{{ warehouse.rows_limits.get(r, {}).get('v', 2) }}" step="0.1" style="width:70px; padding: 6px;"></td>
                </tr>
                {% endfor %}
            </table>
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white; width:100%; margin-top:15px; font-size: 12px;" data-key="set_save">Сохранить</button>
        </form>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('warehouse')" data-key="tab_warehouse">📦 Склад</button>
        <button class="tab-btn" onclick="switchTab('clients')" data-key="tab_clients">👥 Клиенты</button>
        <button class="tab-btn" onclick="switchTab('orders')" data-key="tab_orders">📋 Заказы</button>
        <button class="tab-btn" onclick="switchTab('statistics')" data-key="tab_statistics">📊 Статистика</button>
        <button class="tab-btn" onclick="switchTab('history')" data-key="tab_history">📜 История</button>
    </div>

    <!-- ВКЛАДКА: СКЛАД -->
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
                    <div style="font-size:9px; color:var(--text-muted); margin-bottom:5px;" data-key="cell_l">1 ячейка:</div>
                    <div style="font-size:9px;">{{ stat.max_w }} кг | {{ stat.max_v }} м³</div>
                    <h2 style="margin:5px 0; color:var(--accent); font-size: 22px;">{{ r }}</h2>
                    <div style="font-size:9px; color:var(--text-muted); margin:5px 0;" data-key="gral">Вся группа:</div>
                    <div style="font-size:9px;">{{ (stat.max_w * num_cells_in_row)|round(1) }} кг | {{ (stat.max_v * num_cells_in_row)|round(2) }} м³</div>
                    <hr style="border:none; border-top:1px solid var(--border); width:100%; margin:5px 0;">
                    <div style="font-size:10px;">Занято:<br>{{ stat.w|round(1) }} кг<br>{{ stat.v|round(2) }} м³</div>
                </div>
                <div class="cells-grid">
                    {% for c in range(1, num_cells_in_row + 1) %}
                        {% set addr = r ~ c|string %}
                        {% set item = warehouse.cells.get(addr) %}
                        {% set exp_status = warehouse.get_expiry_status(item.expiry if item else None) %}
                        <div class="cell {% if item %}occupied{% endif %} {% if exp_status == 'expired' %}expired{% elif exp_status == 'expiring_soon' %}expiring-soon{% endif %}"
                             onclick="{% if item %}openCellEditor('{{ addr }}', '{{ item.name }}', {{ item.qty }}, {{ item.price }}, {{ item.weight }}, {{ item.vol }}, '{{ item.expiry or '' }}'){% else %}setCell('{{ addr }}'){% endif %}">
                            <span style="position:absolute; top:3px; left:4px; font-size:9px; opacity:0.6;">{{ addr }}</span>
                            {% if item %}
                                <div style="margin-top:10px; font-size: 10px;">{{ item.name }}</div>
                                <div style="font-weight: bold;">{{ item.qty }}</div>
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
                    <div class="unit">шт.</div>
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
                    <th data-key="th_status">Статус</th>
                </tr>
            </thead>
            <tbody>
                {% for addr, item in warehouse.cells.items() if item %}
                {% set exp_status = warehouse.get_expiry_status(item.expiry) %}
                <tr {% if exp_status == 'expired' %}style="background-color: rgba(255, 71, 87, 0.3);"{% elif exp_status == 'expiring_soon' %}style="background-color: rgba(255, 165, 2, 0.2);"{% endif %}>
                    <td><b>{{ addr }}</b></td>
                    <td>{{ item.name }}</td>
                    <td><span class="qty-display">{{ item.qty }}</span> шт.</td>
                    <td id="price-{{ addr }}">{{ item.price }}</td>
                    <td>{{ (item.qty * item.weight)|round(1) }}</td>
                    <td>{{ (item.qty * item.vol)|round(3) }}</td>
                    <td>{% if item.expiry %}<span {% if exp_status == 'expired' %}style="color:var(--danger); font-weight:bold;"{% elif exp_status == 'expiring_soon' %}style="color:var(--warning); font-weight:bold;"{% endif %}>{{ item.expiry }}</span>{% else %}-{% endif %}</td>
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

    <!-- ВКЛАДКА: КЛИЕНТЫ -->
    <div id="clients" class="tab-content">
        <h2 data-key="clients_title" style="color:var(--accent); font-size: 18px;">👥 Управление клиентами</h2>
        
        <form action="/add_client" method="POST" class="form-row">
            <input name="name" placeholder="Имя клиента" required data-key="f_client_name">
            <input name="phone" placeholder="Телефон" required data-key="f_client_phone">
            <input name="email" placeholder="Email" type="email" data-key="f_client_email">
            <textarea name="address" placeholder="Адрес доставки" data-key="f_client_address" style="grid-column: span 2;"></textarea>
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white; grid-column: span 2; font-size: 12px;" data-key="btn_add">Добавить клиента</button>
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
                    <td id="balance-{{ client_id }}">{{ "%.2f"|format(client.balance) }} <span class="currency-display">₽</span></td>
                    <td id="spent-{{ client_id }}">{{ "%.2f"|format(client.get('total_spent', 0)) }} <span class="currency-display">₽</span></td>
                    <td>
                        <button class="action-btn" onclick="addPayment('{{ client_id }}', '{{ client.name }}')">💰</button>
                        <button class="action-btn delete" onclick="deleteClient('{{ client_id }}')">🗑️</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- ВКЛАДКА: ЗАКАЗЫ -->
    <div id="orders" class="tab-content">
        <h2 data-key="orders_title" style="color:var(--accent); font-size: 18px;">📋 Заказы и платежи</h2>
        
        <form id="order-form" action="/add_order" method="POST" class="form-row">
            <select name="client_id" id="order-client" required style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); font-size: 12px;">
                <option value="" data-key="f_select_client">Выберите клиента...</option>
                {% for client_id, client in warehouse.clients.items() %}
                <option value="{{ client_id }}">{{ client.name }}</option>
                {% endfor %}
            </select>
            <div style="grid-column: span 2;">
                <label data-key="f_order_items_label">Товары заказа (Ячейка или название):</label>
                <div style="display: grid; grid-template-columns: 1fr 100px; gap: 10px; margin-top: 10px;">
                    <input type="text" id="order-item-addr" placeholder="A1" style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main);">
                    <input type="number" id="order-item-qty" placeholder="Кол-во" min="1" style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main);">
                    <button type="button" onclick="addOrderItem()" class="action-btn success" style="grid-column: span 2;">+ Добавить товар</button>
                </div>
                <div id="order-items-list" style="margin-top: 10px;"></div>
            </div>
            <div id="item-warning" class="warning-notification" style="grid-column: span 2;"></div>
            <input name="amount" type="number" step="0.01" placeholder="Сумма заказа" id="order-amount" required data-key="f_order_amount" min="0" style="grid-column: span 2;">
            <select name="status" style="padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); font-size: 12px; grid-column: span 2;" id="order-status">
                <option value="pending" data-key="order_status_pending">⏳ В обработке</option>
                <option value="completed" data-key="order_status_completed">✓ Завершён</option>
                <option value="returned" data-key="order_status_returned">↩️ Возврат</option>
            </select>
            <button type="submit" class="lang-btn" style="background:var(--accent); color:white; grid-column: span 2; font-size: 12px;" data-key="btn_create">Создать заказ</button>
        </form>

        <table class="orders-table">
            <thead>
                <tr>
                    <th data-key="th_order_id">ID</th>
                    <th data-key="th_order_client">Клиент</th>
                    <th data-key="th_order_items">Товары</th>
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
                    <td>
                        {% for addr, qty in order.items.items() %}
                            <div class="order-item-display">
                                <span class="addr">{{ addr }}</span>:
                                <span class="qty">{{ qty }} шт</span>
                            </div>
                        {% endfor %}
                    </td>
                    <td id="order-amount-{{ order_id }}">{{ "%.2f"|format(order.amount) }} <span class="currency-display">₽</span></td>
                    <td>
                        <select class="status-badge status-{{ order.status }}" onchange="updateOrderStatus('{{ order_id }}', this.value)" style="border:none; background:transparent; padding:0; cursor:pointer;">
                            <option value="pending" {% if order.status == 'pending' %}selected{% endif %} data-key="order_status_pending">⏳ В обработке</option>
                            <option value="completed" {% if order.status == 'completed' %}selected{% endif %} data-key="order_status_completed">✓ Завершён</option>
                            <option value="returned" {% if order.status == 'returned' %}selected{% endif %} data-key="order_status_returned">↩️ Возврат</option>
                        </select>
                    </td>
                    <td>{% if order.paid %}<span style="color:var(--success); font-weight:bold;">✓ Да</span>{% else %}<span style="color:var(--danger);">❌ Нет</span>{% endif %}</td>
                    <td>{{ order.created[:10] }}</td>
                    <td>
                        {% if not order.paid %}<button class="action-btn" onclick="markPaid('{{ order_id }}')">💳</button>{% endif %}
                        <button class="action-btn delete" onclick="deleteOrder('{{ order_id }}')">🗑️</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- ВКЛАДКА: СТАТИСТИКА -->
    <div id="statistics" class="tab-content">
        <h2 data-key="tab_statistics" style="color:var(--accent); font-size: 18px;">📊 Статистика</h2>
        
        <div class="stat-grid">
            <div class="stat-card">
                <h3 data-key="stat_supplies">📦 Поставки товара</h3>
                <canvas id="chart-supplies"></canvas>
            </div>
            <div class="stat-card">
                <h3 data-key="stat_sales">💰 Продажи</h3>
                <canvas id="chart-sales"></canvas>
            </div>
            <div class="stat-card">
                <h3 data-key="stat_inventory">📈 Остатки по группам</h3>
                <canvas id="chart-inventory"></canvas>
            </div>
        </div>

        <div style="background: var(--bg-input); padding: 20px; border-radius: 16px; border: 2px solid var(--accent); margin-top: 20px;">
            <h3 data-key="stat_details">Детальная статистика</h3>
            <div id="stats-details"></div>
        </div>
    </div>

    <!-- ВКЛАДКА: ИСТОРИЯ -->
    <div id="history" class="tab-content">
        <h2 data-key="tab_history" style="color:var(--accent); font-size: 18px;">📜 История операций</h2>
        
        <div class="history-filters">
            <button class="lang-btn active" onclick="filterHistory('all')" data-key="history_all">Все</button>
            <button class="lang-btn" onclick="filterHistory('supply')" data-key="history_supply">Поставки</button>
            <button class="lang-btn" onclick="filterHistory('sale')" data-key="history_sale">Продажи</button>
            <button class="lang-btn" onclick="filterHistory('purchase')" data-key="history_purchase">Покупки</button>
            <button class="lang-btn" onclick="filterHistory('transaction')" data-key="history_transaction">Транзакции</button>
        </div>

        <div class="history-list" id="history-list"></div>
    </div>

</div>

<!-- МОДАЛЬНОЕ ОКНО: РЕДАКТИРОВАНИЕ ЯЧЕЙКИ -->
<div id="cell-modal" class="modal-overlay" onclick="closeCellModal()">
<div class="modal-content" onclick="event.stopPropagation()">
    <h2 id="m-title" style="color:var(--accent); margin-top:0; font-size: 18px;"></h2>
    <form id="cell-edit-form">
        <div style="margin-bottom: 15px;">
            <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="f_item">Название:</label>
            <input type="text" id="m-item-name" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
            <div>
                <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="f_qty">Кол-во:</label>
                <input type="number" id="m-item-qty" min="1" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
            </div>
            <div>
                <label style="font-weight: bold; display: block; margin-bottom: 5px;">Цена (₽):</label>
                <input type="number" id="m-item-price" step="0.01" min="0" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
            </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
            <div>
                <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="f_weight">Вес (кг):</label>
                <input type="number" id="m-item-weight" step="0.01" min="0" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
            </div>
            <div>
                <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="f_vol">Объем (м³):</label>
                <input type="number" id="m-item-vol" step="0.01" min="0" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
            </div>
        </div>
        <div style="margin-bottom: 15px;">
            <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="f_expiry">Срок годности:</label>
            <input type="date" id="m-item-expiry" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
        </div>
        <div style="margin-bottom: 15px;">
            <label style="font-weight: bold; display: block; margin-bottom: 5px;" data-key="export_qty">Отгрузить (шт):</label>
            <input type="number" id="m-item-export" min="0" value="0" style="width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg-card); color:var(--text-main); box-sizing:border-box;">
        </div>
        <input type="hidden" id="m-addr-input">
        <div class="modal-buttons">
            <button type="button" class="modal-btn primary" onclick="saveCellChanges()" data-key="m_apply">Сохранить</button>
            <button type="button" class="modal-btn danger" onclick="fullDeleteCell()" data-key="m_clear">Освободить</button>
        </div>
    </form>
</div>
</div>

{% endif %}

<footer>
<div style="font-weight:bold; font-size:14px; margin-bottom: 10px;">🏆 QAQ Team (РФМЛИ)</div>
<div style="display:flex; justify-content:center; gap:40px; flex-wrap:wrap; font-size: 11px;">
    <div><b>Кутаев Магомедрасуслик</b> (@ItsJustMp4_) (6 кл.)<br>TG:@ItsJustMp4_<br>❤️ HEXAGON</div>
    <div><b>Алавов Биймурадик</b> (@GER) (8 кл.)<br>TG: @GER2548<br>❤️ DOTA_2</div>
    <div><b>Кунтуганов Ратмирчик</b> (@C_plus_plus) (8 кл.)<br>TG: @C_plus_plus_is_good<br>❤️ Омнисия</div>
</div>
<div style="margin-top:20px; font-size: 11px; color: var(--footer-text);">📞 Техподдержка: +7 928 587 97-74 | +7 964 005 96-16</div>
</footer>
<script>
// ===== ПЕРЕВОДЫ И КОНФИГУРАЦИЯ =====

const i18n = {
    ru: {
        t_title: "QAQ Умный Склад", auth_title: "Вход в систему", auth_login: "Войти", auth_create: "Создать аккаунт",
        search_ph: "Поиск товара или ячейки...", f_addr: "Ячейка", f_item: "Товар", f_qty: "Кол-во",
        f_price: "Цена ₽", f_weight: "Вес кг", f_vol: "Объем м³", f_expiry: "Срок годности",
        f_price_label: "Цена ₽", f_item_name: "Название", f_order_items_label: "Товары заказа",
        set_title: "⚙️ Управление лимитами", set_manage_rows: "Управление группами", set_limits_title: "Лимиты групп",
        set_add_row: "Добавить группу", set_save: "Сохранить всё", set_cells: "Ячеек в ряду:",
        m_apply: "Сохранить", m_clear: "Освободить", export_qty: "Отгрузить (шт)",
        nav_exit: "Выход", btn_logout: "Выход", btn_add: "Добавить", btn_create: "Создать заказ",
        summary_title: "📊 Смета склада", sum_qty: "Общее количество", sum_weight: "Общий вес",
        sum_volume: "Общий объем", sum_price: "Общая стоимость", items_list_title: "📋 Список товаров",
        sum_expired: "⚠️ Испорчено", sum_expiring: "⏰ Испортится", th_status: "Статус",
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
        error_overflow_weight: "⚠️ Превышен лимит ПО ВЕСУ! Максимум для группы:",
        error_overflow_volume: "⚠️ Превышен лимит ПО ОБЪЁМУ! Максимум для группы:",
        tab_warehouse: "📦 Склад", tab_clients: "👥 Клиенты", tab_orders: "📋 Заказы",
        tab_statistics: "📊 Статистика", tab_history: "📜 История",
        clients_title: "👥 Управление клиентами", f_client_name: "Имя клиента", f_client_phone: "Телефон",
        f_client_email: "Email", f_client_address: "Адрес доставки", th_client_name: "Имя",
        th_client_phone: "Телефон", th_client_email: "Email", th_client_balance: "Баланс",
        th_client_spent: "Потрачено", th_client_actions: "Действия", orders_title: "📋 Заказы и платежи",
        f_select_client: "Выберите клиента...", f_order_items: "Адрес:кол-во (A1:2,B3:5)",
        f_order_amount: "Сумма заказа", th_order_items: "Товары",
        th_order_id: "ID", th_order_client: "Клиент", th_order_amount: "Сумма",
        th_order_status: "Статус", th_order_date: "Дата", th_order_actions: "Действия",
        th_order_paid: "Оплачен",
        order_status_pending: "⏳ В обработке",
        order_status_completed: "✓ Завершён",
        order_status_returned: "↩️ Возврат",
        item_not_on_warehouse: "⚠️ Товара нет на складе!",
        stat_supplies: "📦 Поставки товара",
        stat_sales: "💰 Продажи",
        stat_inventory: "📈 Остатки по группам",
        stat_details: "📊 Детальная статистика",
        history_all: "Все",
        history_supply: "Поставки",
        history_sale: "Продажи",
        history_purchase: "Покупки",
        history_transaction: "Транзакции",
        cell_l: "1 ячейка:",
        kg: "кг",
        m3: "м³",
        gral: "Вся группа:",
    },
    en: {
        t_title: "QAQ Smart Storage", auth_title: "System Login", auth_login: "Login", auth_create: "Create Account",
        search_ph: "Search item or cell...", f_addr: "Cell", f_item: "Item", f_qty: "Qty",
        f_price: "Price $", f_weight: "Weight kg", f_vol: "Volume m³", f_expiry: "Expiry Date",
        f_price_label: "Price $", f_item_name: "Name", f_order_items_label: "Order Items",
        set_title: "⚙️ Manage Limits", set_manage_rows: "Manage Groups", set_limits_title: "Group Limits",
        set_add_row: "Add Group", set_save: "Save All", set_cells: "Cells per row:",
        m_apply: "Save", m_clear: "Clear", export_qty: "Dispatch (pcs)",
        nav_exit: "Logout", btn_logout: "Logout", btn_add: "Add", btn_create: "Create Order",
        summary_title: "📊 Warehouse Summary", sum_qty: "Total Quantity", sum_weight: "Total Weight",
        sum_volume: "Total Volume", sum_price: "Total Cost", items_list_title: "📋 Items List",
        sum_expired: "⚠️ Expired", sum_expiring: "⏰ Expiring Soon", th_status: "Status",
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
        error_overflow_weight: "⚠️ Weight limit exceeded! Maximum for group:",
        error_overflow_volume: "⚠️ Volume limit exceeded! Maximum for group:",
        tab_warehouse: "📦 Warehouse", tab_clients: "👥 Clients", tab_orders: "📋 Orders",
        tab_statistics: "📊 Statistics", tab_history: "📜 History",
        clients_title: "👥 Manage Clients", f_client_name: "Client Name", f_client_phone: "Phone",
        f_client_email: "Email", f_client_address: "Delivery Address", th_client_name: "Name",
        th_client_phone: "Phone", th_client_email: "Email", th_client_balance: "Balance",
        th_client_spent: "Spent", th_client_actions: "Actions", orders_title: "📋 Orders & Payments",
        f_select_client: "Select Client...", f_order_items: "Address:qty (A1:2,B3:5)",
        f_order_amount: "Order Amount", th_order_items: "Items",
        th_order_id: "ID", th_order_client: "Client", th_order_amount: "Amount",
        th_order_status: "Status", th_order_date: "Date", th_order_actions: "Actions",
        th_order_paid: "Paid",
        order_status_pending: "⏳ Pending",
        order_status_completed: "✓ Completed",
        order_status_returned: "↩️ Returned",
        item_not_on_warehouse: "⚠️ Item not in warehouse!",
        stat_supplies: "📦 Supplies",
        stat_sales: "💰 Sales",
        stat_inventory: "📈 Inventory by Groups",
        stat_details: "📊 Detailed Statistics",
        history_all: "All",
        history_supply: "Supplies",
        history_sale: "Sales",
        history_purchase: "Purchases",
        history_transaction: "Transactions",
        cell_l: "1 cell:",
        kg: "kg",
        m3: "m³",
        gral: "Whole group:",
    },
    cn: {
        t_title: "QAQ 智能仓库", auth_title: "系统登录", auth_login: "登录", auth_create: "创建账户",
        search_ph: "搜索商品或库位...", f_addr: "库位", f_item: "名称", f_qty: "数量",
        f_price: "价格 ¥", f_weight: "重量 kg", f_vol: "体积 m³", f_expiry: "有效期",
        f_price_label: "价格 ¥", f_item_name: "名称", f_order_items_label: "订单商品",
        set_title: "⚙️ 管理限制", set_manage_rows: "管理分组", set_limits_title: "分组限制",
        set_add_row: "添加分组", set_save: "全部保存", set_cells: "每行数量:",
        m_apply: "保存", m_clear: "清空", export_qty: "出库(件)",
        nav_exit: "退出", btn_logout: "退出", btn_add: "添加", btn_create: "创建订单",
        summary_title: "📊 仓库清单", sum_qty: "总数量", sum_weight: "总重量",
        sum_volume: "总体积", sum_price: "总价格", items_list_title: "📋 商品列表",
        sum_expired: "⚠️ 已过期", sum_expiring: "⏰ 即将过期", th_status: "状态",
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
        error_overflow_weight: "⚠️ 超过重量限制! 最大值:",
        error_overflow_volume: "⚠️ 超过体积限制! 最大值:",
        tab_warehouse: "📦 仓库", tab_clients: "👥 客户", tab_orders: "📋 订单",
        tab_statistics: "📊 统计", tab_history: "📜 历史",
        clients_title: "👥 管理客户", f_client_name: "客户名称", f_client_phone: "电话",
        f_client_email: "邮箱", f_client_address: "配送地址", th_client_name: "名称",
        th_client_phone: "电话", th_client_email: "邮箱", th_client_balance: "余额",
        th_client_spent: "消费", th_client_actions: "操作", orders_title: "📋 订单和付款",
        f_select_client: "选择客户...", f_order_items: "库位:数量 (A1:2,B3:5)",
        f_order_amount: "订单金额", th_order_items: "商品",
        th_order_id: "ID", th_order_client: "客户", th_order_amount: "金额",
        th_order_status: "状态", th_order_date: "日期", th_order_actions: "操作",
        th_order_paid: "已付",
        order_status_pending: "⏳ 处理中",
        order_status_completed: "✓ 已完成",
        order_status_returned: "↩️ 已退货",
        item_not_on_warehouse: "⚠️ 仓库中无此商品!",
        stat_supplies: "📦 供应",
        stat_sales: "💰 销售",
        stat_inventory: "📈 按组库存",
        stat_details: "📊 详细统计",
        history_all: "全部",
        history_supply: "供应",
        history_sale: "销售",
        history_purchase: "采购",
        history_transaction: "交易",
        cell_l: "1个库位:",
        kg: "公斤",
        m3: "m³",
        gral: "整个分组:",
    }
};

const currencyRates = {
    'RUB': { symbol: '₽', rate: 1.0 },
    'USD': { symbol: '$', rate: 0.011 },
    'EUR': { symbol: '€', rate: 0.010 },
    'CNY': { symbol: '¥', rate: 0.077 }
};

const cellsData = {{ warehouse.cells|tojson if warehouse else '{}' }};
let activeGroups = {{ warehouse.rows|tojson if warehouse else '[]' }};
let rowConfigs = {{ warehouse.row_configs|tojson if warehouse else '{}' }};
let currentLang = localStorage.getItem('lang') || 'ru';
let currentCurrency = localStorage.getItem('currency') || 'RUB';
let orderItemsBuffer = {};
let chartsInstance = {};
let currentHistoryFilter = 'all';

// ===== ФУНКЦИИ ВАЛЮТ И ПЕРЕВОДА =====

function convertPrice(priceInRub) {
    const rate = currencyRates[currentCurrency]?.rate || 1.0;
    return (priceInRub * rate).toFixed(2);
}

function getCurrencySymbol() {
    return currencyRates[currentCurrency]?.symbol || '₽';
}

function updateCurrencyDisplay() {
    const symbol = getCurrencySymbol();
    document.querySelectorAll('.currency-display').forEach(el => {
        el.textContent = symbol;
    });
    document.querySelectorAll('[id^="price-"]').forEach(el => {
        const addr = el.id.replace('price-', '');
        const basePrice = cellsData[addr]?.price || 0;
        el.textContent = convertPrice(basePrice);
    });
    document.querySelectorAll('[id^="balance-"]').forEach(el => {
        const txt = el.textContent;
        const baseBalance = parseFloat(txt.split(' ')[0]) || 0;
        el.textContent = convertPrice(baseBalance / (currencyRates[currentCurrency].rate || 1.0)) + ' ' + symbol;
    });
}

function setCurrency(curr) {
    currentCurrency = curr;
    localStorage.setItem('currency', curr);
    updateCurrencyDisplay();
    renderCurrencyButtons();
}

function renderCurrencyButtons() {
    const container = document.getElementById('currency-selector');
    if (!container) return;
    
    container.innerHTML = '';
    for (const [code, data] of Object.entries(currencyRates)) {
        const btn = document.createElement('button');
        btn.className = `currency-btn ${code === currentCurrency ? 'active' : ''}`;
        btn.textContent = `${code} (${data.symbol})`;
        btn.onclick = () => setCurrency(code);
        container.appendChild(btn);
    }
}

function setLang(lang) {
    localStorage.setItem('lang', lang);
    currentLang = lang;
    const d = i18n[lang];
    
    document.querySelectorAll('.lang-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`lang-${lang}`)?.classList.add('active');
    
    document.querySelectorAll('[data-key]').forEach(el => {
        const k = el.getAttribute('data-key');
        const text = d[k] || k;
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = text;
        else if (el.tagName === 'OPTION') el.innerText = text;
        else if (el.tagName === 'LABEL') el.innerText = text;
        else el.innerText = text;
    });
    
    const authUsername = document.getElementById('auth-username');
    const authPassword = document.getElementById('auth-password');
    if(authUsername) authUsername.placeholder = d.auth_username;
    if(authPassword) authPassword.placeholder = d.auth_password;
    
    updateCurrencyDisplay();
}

// ===== ФУНКЦИИ ВКЛАДОК =====

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
    
    if (tabName === 'statistics') {
        setTimeout(renderStatistics, 100);
    } else if (tabName === 'history') {
        setTimeout(loadHistory, 100);
    }
}

// ===== ФУНКЦИИ ОШИБОК =====

function showError(message) {
    const errorDiv = document.getElementById('error-notification');
    if (errorDiv) {
        const d = i18n[currentLang];
        let displayMessage = message;
        
        if (message.includes('OVERFLOW_WEIGHT')) {
            const parts = message.split('|');
            const group = parts[2] || 'неизвестно';
            displayMessage = d.error_overflow_weight + ' ' + group;
        } else if (message.includes('OVERFLOW_VOLUME')) {
            const parts = message.split('|');
            const group = parts[2] || 'неизвестно';
            displayMessage = d.error_overflow_volume + ' ' + group;
        } else if (message.startsWith('ERROR_')) {
            displayMessage = d[message] || message;
        } else if (message.includes('|')) {
            const key = message.split('|')[0];
            displayMessage = d[key] || message;
        }
        
        errorDiv.textContent = displayMessage;
        errorDiv.classList.add('show');
        setTimeout(() => {
            errorDiv.classList.remove('show');
        }, 5000);
    }
}

// ===== ФУНКЦИИ ПОИСКА =====

function doSearch() {
    const q = document.getElementById('search').value.toUpperCase();
    const dropdown = document.getElementById('search-dropdown');
    if(!q) { dropdown.style.display = 'none'; return; }
    
    let html = '';
    for(let addr in cellsData) {
        const item = cellsData[addr];
        if(item && (item.name.toUpperCase().includes(q) || addr.includes(q))) {
            const price = convertPrice(item.price);
            html += `<div class="search-item" onclick="openCellEditor('${addr}', '${item.name.replace(/'/g, "\\'")}', ${item.qty}, ${item.price}, ${item.weight}, ${item.vol}, '${item.expiry || ''}')">
                <b>${addr}</b> - ${item.name} (${item.qty} шт)<br>
                <small>${getCurrencySymbol()}${price} | ${item.weight}kg | ${item.vol}m³</small>
            </div>`;
        }
    }
    dropdown.innerHTML = html || '<div class="search-item">Не найдено</div>';
    dropdown.style.display = 'block';
}

// ===== ФУНКЦИИ НАСТРОЕК =====

function toggleSettings() {
    const p = document.getElementById('settings-panel');
    p.style.display = p.style.display === 'block' ? 'none' : 'block';
    if(p.style.display === 'block') renderGroupsUI();
}

function syncActiveGroupsFromDOM() {
    const container = document.getElementById('groups-container');
    if (!container) return;
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
    const allRows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T'];
    const available = allRows.filter(r => !activeGroups.includes(r));
    if(available.length === 0) {
        showError(i18n[currentLang].error_invalid);
        return;
    }
    const newGroup = available[0];
    activeGroups.push(newGroup);
    rowConfigs[newGroup] = {num_cells: 10};
    renderGroupsUI();
}

function removeGroup(group) {
    const d = i18n[currentLang];
    if(confirm(`Удалить группу ${group}?`)) {
        activeGroups = activeGroups.filter(r => r !== group);
        delete rowConfigs[group];
        renderGroupsUI();
    }
}

// ===== ФУНКЦИИ ЯЧЕЕК =====

function setCell(a) {
    document.getElementById('p-addr').value = a;
    switchTab('warehouse');
    setTimeout(() => {
        document.getElementById('p-addr').focus();
    }, 100);
}

function openCellEditor(addr, name, qty, price, weight, vol, expiry) {
    const d = i18n[currentLang];
    document.getElementById('m-title').innerText = addr + " | " + name;
    document.getElementById('m-item-name').value = name;
    document.getElementById('m-item-qty').value = qty;
    document.getElementById('m-item-price').value = price.toFixed(2);
    document.getElementById('m-item-weight').value = weight.toFixed(2);
    document.getElementById('m-item-vol').value = vol.toFixed(2);
    document.getElementById('m-item-expiry').value = expiry;
    document.getElementById('m-item-export').value = 0;
    document.getElementById('m-addr-input').value = addr;
    document.getElementById('cell-modal').style.display = 'flex';
}

function closeCellModal() {
    document.getElementById('cell-modal').style.display = 'none';
}

function saveCellChanges() {
    const addr = document.getElementById('m-addr-input').value;
    const name = document.getElementById('m-item-name').value;
    const qty = parseInt(document.getElementById('m-item-qty').value) || 0;
    const price = parseFloat(document.getElementById('m-item-price').value) || 0;
    const weight = parseFloat(document.getElementById('m-item-weight').value) || 0;
    const vol = parseFloat(document.getElementById('m-item-vol').value) || 0;
    const expiry = document.getElementById('m-item-expiry').value;
    const exportQty = parseInt(document.getElementById('m-item-export').value) || 0;

    if (qty <= 0) {
        showError(i18n[currentLang].error_invalid_qty);
        return;
    }

    if (exportQty > 0 && exportQty > qty) {
        showError(i18n[currentLang].error_insufficient_qty);
        return;
    }

    const finalQty = qty - exportQty;
    window.location.href = `/update_item/${addr}?qty=${finalQty}&name=${encodeURIComponent(name)}&price=${price}&weight=${weight}&vol=${vol}&expiry=${expiry}`;
}

function fullDeleteCell() {
    if(confirm(i18n[currentLang].m_clear + "? " + document.getElementById('m-addr-input').value)) {
        window.location.href="/delete/"+document.getElementById('m-addr-input').value;
    }
}

// ===== ФУНКЦИИ ЗАКАЗОВ =====

function addOrderItem() {
    const addr = document.getElementById('order-item-addr').value.trim().toUpperCase();
    const qty = parseInt(document.getElementById('order-item-qty').value) || 0;
    
    const d = i18n[currentLang];
    
    if (!addr || qty <= 0) {
        showError(d.error_invalid);
        return;
    }
    
    let found = false;
    let targetAddr = addr;
    
    // Проверка по адресу ячейки
    if (cellsData[addr]) {
        if (!cellsData[addr]) {
            showError(d.error_item_not_found + addr);
            return;
        }
        found = true;
        targetAddr = addr;
    } else {
        // Проверка по названию товара
        for (let cell in cellsData) {
            if (cellsData[cell] && cellsData[cell].name.toUpperCase() === addr) {
                found = true;
                targetAddr = cell;
                break;
            }
        }
        if (!found) {
            showError(d.error_item_not_found + addr);
            return;
        }
    }
    
    if (cellsData[targetAddr]) {
        if (cellsData[targetAddr].qty < qty) {
            showError(d.error_insufficient_qty + targetAddr);
            return;
        }
        orderItemsBuffer[targetAddr] = qty;
    }
    
    renderOrderItemsList();
    document.getElementById('order-item-addr').value = '';
    document.getElementById('order-item-qty').value = '';
    updateOrderAmount();
}

function renderOrderItemsList() {
    const list = document.getElementById('order-items-list');
    list.innerHTML = '';
    
    let totalAmount = 0;
    for (let addr in orderItemsBuffer) {
        const qty = orderItemsBuffer[addr];
        const item = cellsData[addr];
        if (item) {
            const itemPrice = item.price * qty * 1.1; // 10% наценка
            totalAmount += itemPrice;
            
            const itemDiv = document.createElement('div');
            itemDiv.className = 'order-item-display';
            itemDiv.innerHTML = `
                <span class="addr">${addr}</span>:
                <span class="qty">${qty} шт</span> ×
                <span class="price">${getCurrencySymbol()}${convertPrice(item.price)} = ${getCurrencySymbol()}${convertPrice(itemPrice)}</span>
                <button type="button" onclick="removeOrderItem('${addr}')" style="float:right; background:var(--danger); color:white; border:none; padding:3px 8px; border-radius:4px; cursor:pointer; font-size:11px;">✕</button>
            `;
            list.appendChild(itemDiv);
        }
    }
    
    document.getElementById('order-amount').value = convertPrice(totalAmount);
}

function removeOrderItem(addr) {
    delete orderItemsBuffer[addr];
    renderOrderItemsList();
    updateOrderAmount();
}

function updateOrderAmount() {
    let totalAmount = 0;
    for (let addr in orderItemsBuffer) {
        const qty = orderItemsBuffer[addr];
        const item = cellsData[addr];
        if (item) {
            totalAmount += item.price * qty * 1.1;
        }
    }
    document.getElementById('order-amount').value = convertPrice(totalAmount);
}

// Интеграция с формой заказа
document.addEventListener('DOMContentLoaded', function() {
    const orderForm = document.getElementById('order-form');
    if (orderForm) {
        orderForm.addEventListener('submit', function(e) {
            const clientId = document.getElementById('order-client').value;
            if (!clientId) {
                e.preventDefault();
                showError(i18n[currentLang].error_no_client);
                return;
            }
            
            if (Object.keys(orderItemsBuffer).length === 0) {
                e.preventDefault();
                showError(i18n[currentLang].error_no_items);
                return;
            }
            
            // Создаем скрытое поле для товаров
            let itemsStr = '';
            for (let addr in orderItemsBuffer) {
                itemsStr += addr + ':' + orderItemsBuffer[addr] + ',';
            }
            itemsStr = itemsStr.slice(0, -1);
            
            let orderItemsInput = document.querySelector('input[name="order_items"]');
            if (!orderItemsInput) {
                orderItemsInput = document.createElement('input');
                orderItemsInput.type = 'hidden';
                orderItemsInput.name = 'order_items';
                this.appendChild(orderItemsInput);
            }
            orderItemsInput.value = itemsStr;
        });
    }
});

// ===== ФУНКЦИИ КЛИЕНТОВ =====

function addPayment(clientId, clientName) {
    const d = i18n[currentLang];
    const amount = prompt(`${d.th_client_balance} для ${clientName}:`);
    if(amount && !isNaN(parseFloat(amount)) && parseFloat(amount) > 0) {
        window.location.href = `/add_payment/${clientId}/${parseFloat(amount)}`;
    } else if(amount !== null) {
        showError(d.error_invalid_amount);
    }
}

function deleteClient(clientId) {
    const d = i18n[currentLang];
    if(confirm('Удалить клиента?')) {
        window.location.href = `/delete_client/${clientId}`;
    }
}

// ===== ФУНКЦИИ ЗАКАЗОВ (управление) =====

function markPaid(orderId) {
    if(confirm('Отметить заказ как оплаченный?')) {
        window.location.href = `/mark_paid/${orderId}`;
    }
}

function updateOrderStatus(orderId, newStatus) {
    window.location.href = `/update_order_status/${orderId}/${newStatus}`;
}

function deleteOrder(orderId) {
    if(confirm('Удалить заказ?')) {
        window.location.href = `/delete_order/${orderId}`;
    }
}

// ===== ФУНКЦИИ СТАТИСТИКИ =====

function renderStatistics() {
    fetch('/api/statistics')
        .then(r => r.json())
        .then(data => {
            renderChart('chart-supplies', 'bar', data.supplies, i18n[currentLang].stat_supplies, '#2ed573');
            renderChart('chart-sales', 'line', data.sales, i18n[currentLang].stat_sales, '#00bfff');
            renderChart('chart-inventory', 'doughnut', data.inventory, i18n[currentLang].stat_inventory, '#9575cd');
            
            renderStatsDetails(data);
        })
        .catch(e => console.error('Stats error:', e));
}

function renderChart(canvasId, type, data, label, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    if (chartsInstance[canvasId]) {
        chartsInstance[canvasId].destroy();
    }
    
    const ctx = canvas.getContext('2d');
    const labels = Object.keys(data);
    const values = Object.values(data);
    
    if (labels.length === 0) {
        ctx.fillStyle = '#999';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    chartsInstance[canvasId] = new Chart(ctx, {
        type: type,
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                backgroundColor: type === 'doughnut' ? [
                    'rgba(0, 191, 255, 0.6)',
                    'rgba(149, 117, 205, 0.6)',
                    'rgba(46, 213, 115, 0.6)',
                    'rgba(255, 165, 2, 0.6)',
                    'rgba(255, 71, 87, 0.6)',
                    'rgba(100, 200, 150, 0.6)',
                    'rgba(200, 100, 150, 0.6)',
                    'rgba(150, 150, 200, 0.6)',
                    'rgba(200, 150, 100, 0.6)',
                    'rgba(150, 200, 100, 0.6)'
                ] : color,
                borderColor: type === 'doughnut' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.1)',
                borderWidth: type === 'doughnut' ? 2 : 1,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: type === 'doughnut' }
            },
            scales: type === 'doughnut' ? {} : {
                y: { beginAtZero: true }
            }
        }
    });
}

function renderStatsDetails(data) {
    const detailsDiv = document.getElementById('stats-details');
    let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">';
    
    const totalSupplies = Object.values(data.supplies).reduce((a, b) => a + b, 0);
    const totalSales = Object.values(data.sales).reduce((a, b) => a + b, 0);
    const totalInventory = Object.values(data.inventory).reduce((a, b) => a + b, 0);
    
    const d = i18n[currentLang];
    
    html += `
        <div style="background: rgba(46, 213, 115, 0.1); padding: 15px; border-radius: 8px; border-left: 4px solid #2ed573;">
            <div style="font-size: 12px; font-weight: bold;">${d.stat_supplies}</div>
            <div style="font-size: 24px; font-weight: bold; color: #2ed573; margin-top: 10px;">${totalSupplies}</div>
            <div style="font-size: 11px; color: #666; margin-top: 5px;">шт.</div>
        </div>
        <div style="background: rgba(0, 191, 255, 0.1); padding: 15px; border-radius: 8px; border-left: 4px solid #00bfff;">
            <div style="font-size: 12px; font-weight: bold;">${d.stat_sales}</div>
            <div style="font-size: 24px; font-weight: bold; color: #00bfff; margin-top: 10px;">${getCurrencySymbol()}${convertPrice(totalSales)}</div>
            <div style="font-size: 11px; color: #666; margin-top: 5px;">Всего</div>
        </div>
        <div style="background: rgba(149, 117, 205, 0.1); padding: 15px; border-radius: 8px; border-left: 4px solid #9575cd;">
            <div style="font-size: 12px; font-weight: bold;">${d.stat_inventory}</div>
            <div style="font-size: 24px; font-weight: bold; color: #9575cd; margin-top: 10px;">${totalInventory}</div>
            <div style="font-size: 11px; color: #666; margin-top: 5px;">ячеек</div>
        </div>
    `;
    
    html += '</div>';
    detailsDiv.innerHTML = html;
}

// ===== ФУНКЦИИ ИСТОРИИ =====

function filterHistory(type) {
    currentHistoryFilter = type;
    document.querySelectorAll('.history-filters .lang-btn').forEach(btn => btn.classList.remove('active'));
    event.target?.classList.add('active');
    loadHistory();
}

function loadHistory() {
    fetch(`/api/history?filter=${currentHistoryFilter}`)
        .then(r => r.json())
        .then(data => {
            renderHistoryList(data.history);
        })
        .catch(e => console.error('History error:', e));
}

function renderHistoryList(historyData) {
    const list = document.getElementById('history-list');
    list.innerHTML = '';
    
    const d = i18n[currentLang];
    
    if (historyData.length === 0) {
        list.innerHTML = '<div style="text-align: center; padding: 20px; color: #999;">Нет данных</div>';
        return;
    }
    
    for (const entry of historyData) {
        const time = new Date(entry.timestamp).toLocaleString('ru-RU');
        const typeClass = entry.type;
        
        const div = document.createElement('div');
        div.className = `history-item ${typeClass}`;
        
        let content = '';
        if (typeClass === 'supply') {
            content = `${entry.data.name} (${entry.data.qty} шт) → <b>${entry.data.addr}</b>`;
        } else if (typeClass === 'sale') {
            content = `Продажа клиенту ${entry.data.client} - <b>${getCurrencySymbol()}${convertPrice(entry.data.amount)}</b>`;
        } else if (typeClass === 'purchase') {
            content = `Покупка за <b>${getCurrencySymbol()}${convertPrice(entry.data.amount)}</b>`;
        } else if (typeClass === 'transaction') {
            content = `Платеж: ${entry.data.client} - <b>${getCurrencySymbol()}${convertPrice(entry.data.amount)}</b>`;
        }
        
        div.innerHTML = `
            <div class="history-time">⏰ ${time}</div>
            <div class="history-data">${content}</div>
        `;
        
        list.appendChild(div);
    }
}

// ===== ФУНКЦИИ ТЕМЫ =====

function toggleTheme() {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    document.body.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

// ===== ИНИЦИАЛИЗАЦИЯ =====

function initApp() {
    setLang(localStorage.getItem('lang') || 'ru');
    if(localStorage.getItem('theme') === 'dark') document.body.setAttribute('data-theme', 'dark');
    renderCurrencyButtons();
    setCurrency(localStorage.getItem('currency') || 'RUB');
}
</script>
"""
# ===== ЧАСТЬ 11: FLASK МАРШРУТЫ (часть 1/4) - АУТЕНТИФИКАЦИЯ =====

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

# ===== ЧАСТЬ 12: FLASK МАРШРУТЫ (часть 2/4) - ТОВАРЫ И КЛИЕНТЫ =====

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

@app.route('/update_item/<addr>', methods=['GET', 'POST'])
def update_item(addr):
    wh = get_wh()
    if wh:
        try:
            addr = addr.upper().strip()
            
            if request.method == 'POST':
                qty = request.form.get('qty')
                name = request.form.get('name')
                price = request.form.get('price')
                weight = request.form.get('weight')
                vol = request.form.get('vol')
                expiry = request.form.get('expiry')
            else:
                qty = request.args.get('qty')
                name = request.args.get('name')
                price = request.args.get('price')
                weight = request.args.get('weight')
                vol = request.args.get('vol')
                expiry = request.args.get('expiry')
            
            if not addr or addr not in wh.cells:
                return redirect('/')
            
            if wh.cells[addr]:
                if qty:
                    try:
                        new_qty = int(qty)
                        if new_qty <= 0:
                            wh.cells[addr] = None
                        else:
                            wh.cells[addr]['qty'] = new_qty
                            if name:
                                wh.cells[addr]['name'] = name
                            if price:
                                try:
                                    wh.cells[addr]['price'] = float(price)
                                except ValueError:
                                    pass
                            if weight:
                                try:
                                    wh.cells[addr]['weight'] = float(weight)
                                except ValueError:
                                    pass
                            if vol:
                                try:
                                    wh.cells[addr]['vol'] = float(vol)
                                except ValueError:
                                    pass
                            if expiry is not None:
                                wh.cells[addr]['expiry'] = expiry if expiry else None
                    except ValueError:
                        pass
                
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

# ===== ЧАСТЬ 13: FLASK МАРШРУТЫ (часть 3/4) - ЗАКАЗЫ И ПЛАТЕЖИ =====

@app.route('/add_order', methods=['POST'])
def add_order():
    wh = get_wh()
    if wh:
        try:
            client_id = request.form.get('client_id', '').strip()
            items_str = request.form.get('order_items', '').strip()
            amount = request.form.get('amount', '0').strip()
            status = request.form.get('status', 'pending').strip()
            
            if status not in ['pending', 'completed', 'returned']:
                status = 'pending'
            
            if not client_id:
                session['last_error'] = "ERROR_NO_CLIENT"
                return redirect('/')
            
            if not items_str:
                session['last_error'] = "ERROR_NO_ITEMS"
                return redirect('/')
            
            # Парсим товары из строки "A1:2,B3:5"
            order_items = {}
            try:
                item_list = items_str.split(',')
                for item_str in item_list:
                    item_str = item_str.strip()
                    if ':' in item_str:
                        parts = item_str.split(':')
                        addr = parts[0].strip().upper()
                        qty_str = parts[1].strip()
                        
                        try:
                            qty = int(qty_str)
                            if qty > 0 and addr:
                                order_items[addr] = qty
                        except ValueError:
                            pass
            except:
                pass
            
            try:
                amount_float = float(amount)
                if amount_float <= 0:
                    session['last_error'] = "ERROR_INVALID_AMOUNT"
                    return redirect('/')
            except (ValueError, TypeError):
                session['last_error'] = "ERROR_INVALID_AMOUNT"
                return redirect('/')
            
            if not wh.add_order(client_id, order_items, amount_float, status):
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
                                new_qty = max(0, current_qty - need)
                                wh.cells[addr]['qty'] = new_qty
                                if new_qty == 0:
                                    wh.cells[addr] = None
                    order['paid'] = True
                    order['status'] = 'completed'
                    wh.save_orders_data()
                    wh.save_to_backup()
                    add_history_entry(wh.username, "sales", {
                        "order_id": order_id,
                        "amount": order.get('amount', 0),
                        "client": wh.clients.get(order.get('client_id'), {}).get('name', 'Unknown')
                    })
        except Exception:
            pass
    return redirect('/')

@app.route('/update_order_status/<order_id>/<new_status>')
def update_order_status(order_id, new_status):
    wh = get_wh()
    if wh:
        try:
            order_id = order_id.strip()
            if order_id in wh.orders and new_status in ['pending', 'completed', 'returned']:
                wh.orders[order_id]['status'] = new_status
                wh.save_orders_data()
        except Exception:
            pass
    return redirect('/')

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
                add_history_entry(wh.username, "transactions", {
                    "client": wh.clients[client_id]['name'],
                    "amount": amount_float,
                    "type": "payment"
                })
        except (ValueError, TypeError):
            pass
    return redirect('/')

# ===== ЧАСТЬ 14: FLASK МАРШРУТЫ (часть 4/4) - НАСТРОЙКИ И API =====

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

@app.route('/api/statistics')
def api_statistics():
    wh = get_wh()
    if not wh:
        return jsonify({"error": "Not authorized"}), 401
    
    stats = wh.get_statistics()
    
    # Получаем данные по ячейкам для инвентаря
    inventory = {}
    for row in wh.rows:
        inventory[row] = sum(1 for addr in wh.cells if addr.startswith(row) and wh.cells[addr])
    
    return jsonify({
        "supplies": stats.get("supplies", {}),
        "sales": stats.get("sales", {}),
        "inventory": inventory
    })

@app.route('/api/history')
def api_history():
    wh = get_wh()
    if not wh:
        return jsonify({"error": "Not authorized"}), 401
    
    filter_type = request.args.get('filter', 'all')
    history = load_history(wh.username)
    
    result = []
    
    if filter_type in ['all', 'supply']:
        for entry in history.get("supplies", []):
            result.append({
                "type": "supply",
                "timestamp": entry["timestamp"],
                "data": entry["data"]
            })
    
    if filter_type in ['all', 'sale']:
        for entry in history.get("sales", []):
            result.append({
                "type": "sale",
                "timestamp": entry["timestamp"],
                "data": entry["data"]
            })
    
    if filter_type in ['all', 'purchase']:
        for entry in history.get("purchases", []):
            result.append({
                "type": "purchase",
                "timestamp": entry["timestamp"],
                "data": entry["data"]
            })
    
    if filter_type in ['all', 'transaction']:
        for entry in history.get("transactions", []):
            result.append({
                "type": "transaction",
                "timestamp": entry["timestamp"],
                "data": entry["data"]
            })
    
    # Сортировка по времени (новые первыми)
    result.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return jsonify({"history": result[:100]})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(port=5001, debug=True)
