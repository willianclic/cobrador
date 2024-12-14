from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import pandas as pd
import os
import urllib.parse

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
                            cobrado INTEGER DEFAULT 0)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            categoria TEXT,
                            texto TEXT,
                            qtd_faturas INTEGER)''')

init_db()

@app.route('/')
def index():
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

        # Ordenar as cidades em ordem alfabética no backend
        cursor.execute("SELECT DISTINCT cidade FROM clientes ORDER BY cidade ASC")
        cidades_disponiveis = [row[0] for row in cursor.fetchall()]

        cursor.execute(f"SELECT COUNT(*) FROM clientes {where_clause}", params)
        total_clients = cursor.fetchone()[0]
        total_pages = (total_clients + per_page - 1) // per_page

        cursor.execute(f"SELECT * FROM clientes {where_clause} LIMIT ? OFFSET ?", (*params, per_page, offset))
        clientes = cursor.fetchall()

        # Fetch messages available for each client
        mensagens_disponiveis = {}
        for cliente in clientes:
            qtd_titulos = cliente[4]
            cursor.execute("SELECT COUNT(*) FROM mensagens WHERE qtd_faturas = ? OR (qtd_faturas = 2 AND ? > 2)", (qtd_titulos, qtd_titulos))
            mensagens_disponiveis[cliente[0]] = cursor.fetchone()[0] > 0

    return render_template(
        'index.html', 
        clientes=clientes, 
        page=page, 
        total_pages=total_pages, 
        search_query=search_query, 
        filter_parcelas=filter_parcelas, 
        cidades_disponiveis=cidades_disponiveis, 
        selected_cidades=filter_cidades,
        filter_nao_cobrados=filter_nao_cobrados,
        mensagens_disponiveis=mensagens_disponiveis
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
            cursor.execute("DELETE FROM clientes")
            conn.commit()
            for _, row in df.iterrows():
                cursor.execute('''INSERT INTO clientes (nome, telefone, cidade, qtd_titulos, total_vencido, cobrado)
                                  VALUES (?, ?, ?, ?, ?, 0)''',
                               (row['nome'], row['telefone'], row['cidade'], row['qtd_titulos'], row['total_vencido']))
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
            qtd_faturas = request.form['qtd_faturas']
            cursor.execute('''INSERT INTO mensagens (categoria, texto, qtd_faturas)
                              VALUES (?, ?, ?)''', (categoria, texto, qtd_faturas))
            conn.commit()

        cursor.execute("SELECT * FROM mensagens")
        mensagens = cursor.fetchall()
    return render_template('mensagens.html', mensagens=mensagens)

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

@app.route('/cobrar/<int:cliente_id>')
def cobrar(cliente_id):
    with sqlite3.connect('cobranca.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, qtd_titulos, total_vencido FROM clientes WHERE id = ?", (cliente_id,))
        cliente = cursor.fetchone()

        if cliente:
            nome, telefone, qtd_titulos, total_vencido = cliente
            cursor.execute("UPDATE clientes SET cobrado = 1 WHERE id = ?", (cliente_id,))
            conn.commit()

            cursor.execute("SELECT texto FROM mensagens WHERE qtd_faturas = ? OR (qtd_faturas = 2 AND ? > 2) ORDER BY id DESC LIMIT 1", (qtd_titulos, qtd_titulos))
            mensagem_custom = cursor.fetchone()

            if not mensagem_custom:
                flash("Nenhuma mensagem personalizada disponível para o número de parcelas em aberto.", "danger")
                return redirect(url_for('index'))

            mensagem = mensagem_custom[0].format(nome=nome.split()[0], qtdparcelas=qtd_titulos, valor=f"R${total_vencido:.2f}")
            mensagem = mensagem.replace("\n", " ")  # Remover quebras de linha
            mensagem_encoded = urllib.parse.quote(mensagem)  # Codificar a mensagem
            whatsapp_link = f"https://wa.me/{telefone}?text={mensagem_encoded}"
            return redirect(whatsapp_link, code=302)

    return redirect(url_for('index'))

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
    app.run(debug=True)
