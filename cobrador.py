from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import sqlite3
import pandas as pd
import os
import urllib.parse
from babel.numbers import format_currency
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database setup
def init_db():
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT,
                            telefone TEXT,
                            cidade TEXT,
                            qtd_titulos INTEGER,
                            total_vencido REAL,
                            cobrado INTEGER DEFAULT 0,
                            valor_com_juros_multa REAL)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            categoria TEXT,
                            texto TEXT,
                            qtd_faturas INTEGER)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            multa REAL DEFAULT 2.75,
                            juros REAL DEFAULT 1.32)''')

        # Garantir que há uma configuração inicial
        cursor.execute("SELECT COUNT(*) FROM configuracoes")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO configuracoes (multa, juros) VALUES (?, ?)", (2.75, 1.32))

init_db()

def formatar_valor(valor):
    if valor is None:
        return "R$0,00"
    return format_currency(valor, 'BRL', locale='pt_BR')

def gerar_cumprimento():
    hora_atual = datetime.now().hour
    if hora_atual < 12:
        return "Bom dia"
    elif hora_atual < 18:
        return "Boa tarde"
    else:
        return ""

@app.route('/')
def index():
    per_page = 50
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '').strip()
    filter_parcelas = request.args.get('parcelas', 'todas')
    filter_cidades = request.args.getlist('cidades')
    filter_cobrados = request.args.get('cobrados', 'todos')  # Novo filtro

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

    if filter_cobrados == 'nao_cobrados':
        where_clauses.append("cobrado = 0")
    elif filter_cobrados == 'cobrados':
        where_clauses.append("cobrado = 1")

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()

        # Carregar cidades disponíveis para o filtro
        cursor.execute("SELECT DISTINCT cidade FROM clientes ORDER BY cidade ASC")
        cidades_disponiveis = [row[0] for row in cursor.fetchall()]

        # Indicadores para o dashboard
        cursor.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_vencido) FROM clientes")
        valor_total = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM clientes WHERE cobrado = 1")
        total_cobrados = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_vencido) FROM clientes WHERE cobrado = 1")
        valor_cobrado = cursor.fetchone()[0] or 0

        total_nao_cobrados = total_clientes - total_cobrados

        # Carregar lista de clientes com os filtros aplicados
        cursor.execute(f"SELECT * FROM clientes {where_clause} LIMIT ? OFFSET ?", (*params, per_page, offset))
        clientes = cursor.fetchall()

        clientes_formatados = []
        for cliente in clientes:
            total_vencido = cliente[5] if cliente[5] is not None else 0
            valor_com_juros_multa = cliente[7] if cliente[7] is not None else 0

            clientes_formatados.append({
                'id': cliente[0],
                'nome': cliente[1],
                'telefone': cliente[2],
                'cidade': cliente[3],
                'qtd_titulos': cliente[4],
                'total_vencido': formatar_valor(total_vencido),
                'valor_com_juros_multa': formatar_valor(valor_com_juros_multa),
                'cobrado': cliente[6]
            })

    return render_template(
        'index.html',
        clientes=clientes_formatados,
        page=page,
        total_pages=(total_clientes + per_page - 1) // per_page,
        search_query=search_query,
        filter_parcelas=filter_parcelas,
        cidades_disponiveis=cidades_disponiveis,
        selected_cidades=filter_cidades,
        filter_cobrados=filter_cobrados,
        total_clientes=total_clientes,
        valor_total=formatar_valor(valor_total),
        total_cobrados=total_cobrados,
        valor_cobrado=formatar_valor(valor_cobrado),
        total_nao_cobrados=total_nao_cobrados
    )
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

    if filter_cobrados == 'nao_cobrados':
        where_clauses.append("cobrado = 0")
    elif filter_cobrados == 'cobrados':
        where_clauses.append("cobrado = 1")

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT cidade FROM clientes ORDER BY cidade ASC")
        cidades_disponiveis = [row[0] for row in cursor.fetchall()]

        cursor.execute(f"SELECT COUNT(*) FROM clientes {where_clause}", params)
        total_clients = cursor.fetchone()[0]
        total_pages = (total_clients + per_page - 1) // per_page

        cursor.execute(f"SELECT * FROM clientes {where_clause} LIMIT ? OFFSET ?", (*params, per_page, offset))
        clientes = cursor.fetchall()

        clientes_formatados = []
        for cliente in clientes:
            total_vencido = cliente[5] if cliente[5] is not None else 0
            valor_com_juros_multa = cliente[7] if cliente[7] is not None else 0

            clientes_formatados.append({
                'id': cliente[0],
                'nome': cliente[1],
                'telefone': cliente[2],
                'cidade': cliente[3],
                'qtd_titulos': cliente[4],
                'total_vencido': formatar_valor(total_vencido),
                'valor_com_juros_multa': formatar_valor(valor_com_juros_multa),
                'cobrado': cliente[6]
            })

    return render_template(
        'index.html', 
        clientes=clientes_formatados, 
        page=page, 
        total_pages=total_pages, 
        search_query=search_query, 
        filter_parcelas=filter_parcelas, 
        cidades_disponiveis=cidades_disponiveis, 
        selected_cidades=filter_cidades,
        filter_cobrados=filter_cobrados
    )

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    if file:
        file_path = os.path.join('uploads', file.filename)
        file.save(file_path)

        df = pd.read_excel(file_path)
        df = process_excel(df)

        with sqlite3.connect('cobranca.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT multa, juros FROM configuracoes")
            multa, juros = cursor.fetchone()

            cursor.execute("DELETE FROM clientes")
            conn.commit()
            for _, row in df.iterrows():
                valor_com_juros_multa = calcular_com_juros_e_multa(row['total_vencido'], multa, juros)
                cursor.execute('''INSERT INTO clientes (nome, telefone, cidade, qtd_titulos, total_vencido, cobrado, valor_com_juros_multa)
                                  VALUES (?, ?, ?, ?, ?, 0, ?)''',
                               (row['nome'], row['telefone'], row['cidade'], row['qtd_titulos'], row['total_vencido'], valor_com_juros_multa))
            conn.commit()

        return redirect(url_for('index'))
    return "No file uploaded!"

@app.route('/mensagens', methods=['GET', 'POST'])
def mensagens():
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        if request.method == 'POST':
            categoria = request.form['categoria']
            texto = request.form['texto']
            qtd_faturas = int(request.form['qtd_faturas'])
            cursor.execute('''INSERT INTO mensagens (categoria, texto, qtd_faturas)
                              VALUES (?, ?, ?)''', (categoria, texto, qtd_faturas))
            conn.commit()

        cursor.execute("SELECT * FROM mensagens")
        mensagens = cursor.fetchall()
    return render_template('mensagens.html', mensagens=mensagens)

@app.route('/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if request.method == 'POST':
        multa = float(request.form['multa'])
        juros = float(request.form['juros'])

        with sqlite3.connect('cobranca.db') as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE configuracoes SET multa = ?, juros = ?", (multa, juros))
            conn.commit()
        flash("Configurações atualizadas com sucesso!", "success")

    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT multa, juros FROM configuracoes")
        configuracoes = cursor.fetchone()

    return render_template('configuracoes.html', configuracoes=configuracoes)

@app.route('/editar_mensagem/<int:mensagem_id>', methods=['GET', 'POST'])
def editar_mensagem(mensagem_id):
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        if request.method == 'POST':
            categoria = request.form['categoria']
            texto = request.form['texto']
            qtd_faturas = request.form['qtd_faturas']
            cursor.execute('''UPDATE mensagens SET categoria = ?, texto = ?, qtd_faturas = ? WHERE id = ?''',
                           (categoria, texto, qtd_faturas, mensagem_id))
            conn.commit()
            return redirect(url_for('mensagens'))

        cursor.execute("SELECT * FROM mensagens WHERE id = ?", (mensagem_id,))
        mensagem = cursor.fetchone()
    return render_template('editar_mensagem.html', mensagem=mensagem)

@app.route('/excluir_mensagem/<int:mensagem_id>', methods=['POST', 'GET'])
def excluir_mensagem(mensagem_id):
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mensagens WHERE id = ?", (mensagem_id,))
        conn.commit()
    return redirect(url_for('mensagens'))

@app.route('/cobrar/<int:cliente_id>', methods=['GET'])
def cobrar(cliente_id):
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, qtd_titulos, total_vencido, valor_com_juros_multa FROM clientes WHERE id = ?", (cliente_id,))
        cliente = cursor.fetchone()

        if cliente:
            nome, telefone, qtd_titulos, total_vencido, valor_com_juros_multa = cliente
            cursor.execute("UPDATE clientes SET cobrado = 1 WHERE id = ?", (cliente_id,))
            conn.commit()

            cursor.execute("SELECT texto FROM mensagens WHERE qtd_faturas = ? OR (qtd_faturas = 2 AND ? > 2) ORDER BY id DESC LIMIT 1", (qtd_titulos, qtd_titulos))
            mensagem_custom = cursor.fetchone()

            if not mensagem_custom:
                return jsonify(success=False, message="Nenhuma mensagem personalizada disponível para o número de parcelas em aberto.")

            cumprimento = gerar_cumprimento()
            mensagem = mensagem_custom[0].format(
                nome=nome.split()[0],
                qtdparcelas=qtd_titulos,
                valor=formatar_valor(total_vencido),
                multa=formatar_valor(2.75),
                juros="1.32%",
                valor_com_juros_multa=formatar_valor(valor_com_juros_multa),
                cumprimento=cumprimento
            )

            mensagem_encoded = urllib.parse.quote(mensagem)  # Codificar a mensagem

            whatsapp_link = f"https://wa.me/{telefone}?text={mensagem_encoded}"
            return jsonify(success=True, link=whatsapp_link)

    return jsonify(success=False, message="Erro ao processar o cliente.")

def calcular_com_juros_e_multa(valor, multa, juros):
    valor_com_multa = valor + multa
    valor_com_juros = valor_com_multa + (valor_com_multa * (juros / 100))
    return round(valor_com_juros, 2)

def process_excel(df):
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
