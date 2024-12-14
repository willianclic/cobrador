from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import sqlite3
import pandas as pd
import os
import urllib.parse

# ======================================
# Sistema de Cobrança por Mensagens (v4)
# ======================================
# Esta versão integra as funcionalidades de "Clientes" e "Mensagens"
# em uma única página, utilizando JavaScript e AJAX para alternância
# dinâmica de conteúdo e operações CRUD (mensagens).
# ======================================

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Inicialização do Banco de Dados
def init_db():
    """Cria as tabelas necessárias caso ainda não existam."""
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT,
                            telefone TEXT,
                            cidade TEXT,
                            qtd_titulos INTEGER,
                            total_vencido REAL,
                            cobrado INTEGER DEFAULT 0)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            categoria TEXT,
                            texto TEXT,
                            qtd_faturas INTEGER)''')

init_db()

# ======================================
# Rotas Principais
# ======================================

@app.route('/')
def index():
    """Exibe a página inicial, que agora inclui abas para clientes e mensagens."""
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()

        # Lista de cidades para filtro
        cursor.execute("SELECT DISTINCT cidade FROM clientes ORDER BY cidade ASC")
        cidades_disponiveis = [row[0] for row in cursor.fetchall()]

        # Mensagens existentes
        cursor.execute("SELECT * FROM mensagens")
        mensagens = cursor.fetchall()

    return render_template('index.html', cidades_disponiveis=cidades_disponiveis, mensagens=mensagens)

# ======================================
# Operações com Clientes
# ======================================

@app.route('/clientes', methods=['GET'])
def get_clientes():
    """Retorna os clientes filtrados no formato JSON para exibição dinâmica."""
    per_page = 50
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '').strip()
    filter_parcelas = request.args.get('parcelas', 'todas')
    filter_cidades = request.args.getlist('cidades')
    filter_nao_cobrados = request.args.get('nao_cobrados', 'off') == 'on'

    offset = (page - 1) * per_page

    where_clauses = []
    params = []

    if search_query:
        where_clauses.append("(nome LIKE ? OR telefone LIKE ?)")
        params.extend((f"%{search_query}%", f"%{search_query}%"))

    if filter_parcelas == '1':
        where_clauses.append("qtd_titulos = 1")
    elif filter_parcelas == '2+':
        where_clauses.append("qtd_titulos > 1")

    if filter_cidades:
        where_clauses.append("cidade IN ({})".format(", ".join(["?"] * len(filter_cidades))))
        params.extend(filter_cidades)

    if filter_nao_cobrados:
        where_clauses.append("cobrado = 0")

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()

        # Total de clientes para paginação
        cursor.execute(f"SELECT COUNT(*) FROM clientes {where_clause}", params)
        total_clients = cursor.fetchone()[0]
        total_pages = (total_clients + per_page - 1) // per_page

        # Clientes filtrados
        cursor.execute(f"SELECT * FROM clientes {where_clause} LIMIT ? OFFSET ?", (*params, per_page, offset))
        clientes = cursor.fetchall()

    return jsonify({
        'clientes': clientes,
        'total_pages': total_pages,
        'current_page': page
    })

# ======================================
# Operações com Mensagens
# ======================================

@app.route('/mensagens', methods=['GET', 'POST', 'DELETE', 'PUT'])
def manage_mensagens():
    """Gerencia mensagens via métodos HTTP para operações dinâmicas."""
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()

        if request.method == 'GET':
            cursor.execute("SELECT * FROM mensagens")
            mensagens = cursor.fetchall()
            return jsonify(mensagens)

        if request.method == 'POST':
            data = request.json
            cursor.execute('''INSERT INTO mensagens (categoria, texto, qtd_faturas) VALUES (?, ?, ?)''',
                           (data['categoria'], data['texto'], data['qtd_faturas']))
            conn.commit()
            return jsonify(success=True)

        if request.method == 'DELETE':
            mensagem_id = request.args.get('id')
            cursor.execute("DELETE FROM mensagens WHERE id = ?", (mensagem_id,))
            conn.commit()
            return jsonify(success=True)

        if request.method == 'PUT':
            data = request.json
            cursor.execute('''UPDATE mensagens SET categoria = ?, texto = ?, qtd_faturas = ? WHERE id = ?''',
                           (data['categoria'], data['texto'], data['qtd_faturas'], data['id']))
            conn.commit()
            return jsonify(success=True)

# ======================================
# Funções Auxiliares
# ======================================

def process_excel(df):
    """Processa a planilha Excel para inserção no banco de dados."""
    df = df[['Pessoa', 'Cidade', 'telefone1', 'Qtd Titulo Vencido', 'Total Vencido']]
    df.rename(columns={
        'Pessoa': 'nome',
        'Cidade': 'cidade',
        'telefone1': 'telefone',
        'Qtd Titulo Vencido': 'qtd_titulos',
        'Total Vencido': 'total_vencido'
    }, inplace=True)

    df['telefone'] = df['telefone'].astype(str).str.replace(r'\D', '', regex=True)
    df['telefone'] = df['telefone'].apply(lambda x: f"55{x}" if len(x) == 11 else None)

    df = df[df['telefone'].notnull()]

    return df

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
