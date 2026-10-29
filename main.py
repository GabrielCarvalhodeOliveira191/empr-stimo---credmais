from flask import Flask, render_template, request, redirect, url_for, session, send_file
from datetime import datetime
from calendar import monthrange
from fpdf import FPDF
from io import BytesIO

app = Flask(__name__, template_folder="Templates", static_folder="static")
app.secret_key = "credmais_chave_local"


def converter_valor(valor):
    valor = str(valor).strip().replace("R$", "").replace(" ", "")

    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")

    return float(valor)


def formatar_reais(valor):
    valor = float(valor)
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_pdf(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def gerar_parcelas(emprestimo):
    parcelas = []
    data = datetime.strptime(emprestimo["data"], "%d/%m/%Y")

    quantidade = emprestimo["quantidade_parcelas"]
    valor_parcela = emprestimo["valor_parcela"]

    for numero in range(1, quantidade + 1):
        mes_total = data.month + numero
        ano = data.year + (mes_total - 1) // 12
        mes = (mes_total - 1) % 12 + 1

        dia = min(data.day, monthrange(ano, mes)[1])
        vencimento = datetime(ano, mes, dia)

        parcelas.append({
            "numero": numero,
            "vencimento": vencimento.strftime("%d/%m/%Y"),
            "valor": valor_parcela,
            "valor_formatado": f"R$ {formatar_reais(valor_parcela)}",
            "status": (
                "Pago"
                if numero <= emprestimo.get("parcelas_pagas", 0)
                else "Pendente"
            )
        })

    return parcelas


@app.route("/")
def inicio():
    return redirect(url_for("detalhes_emprestimos"))


@app.route("/emprestimos/detalhes", endpoint="detalhes_emprestimos")
def detalhes_emprestimos():
    emprestimo = session.get("emprestimo")

    if emprestimo:
        emprestimo["valor_formatado"] = (
            f"R$ {formatar_reais(emprestimo['valor'])}"
        )

        emprestimo["total_formatado"] = (
            f"R$ {formatar_reais(emprestimo['total'])}"
        )

        emprestimo["parcela_formatada"] = (
            f"R$ {formatar_reais(emprestimo['valor_parcela'])}"
        )

        emprestimo["parcelas"] = emprestimo["quantidade_parcelas"]
        emprestimo["lista_parcelas"] = gerar_parcelas(emprestimo)

    return render_template(
        "detalhes_emprestimos.html",
        emprestimo=emprestimo
    )


@app.route("/emprestimo/realizado", methods=["POST"])
def emprestimo_realizado():
    cliente = request.form.get("cliente", "").strip()
    valor_texto = request.form.get("valor", "").strip()
    parcelas_texto = request.form.get("parcelas", "12").strip()
    data_texto = request.form.get("data", "").strip()
    valor_parcela_texto = request.form.get("valor_parcela", "").strip()

    try:
        valor = converter_valor(valor_texto)
        quantidade = int(parcelas_texto)

        if not cliente or valor <= 0 or quantidade < 1:
            raise ValueError

        if quantidade > 600:
            raise ValueError

        if data_texto:
            data_objeto = datetime.strptime(data_texto, "%Y-%m-%d")
            data = data_objeto.strftime("%d/%m/%Y")
        else:
            data = datetime.today().strftime("%d/%m/%Y")

        if valor_parcela_texto:
            valor_parcela = converter_valor(valor_parcela_texto)
        else:
            valor_parcela = round(valor * 1.248 / quantidade, 2)

        if valor_parcela <= 0:
            raise ValueError

    except (ValueError, TypeError, OverflowError):
        return (
            "Dados inválidos. Confira o cliente, os valores, a data e as parcelas.",
            400
        )

    session["emprestimo"] = {
        "cliente": cliente,
        "valor": round(valor, 2),
        "data": data,
        "quantidade_parcelas": quantidade,
        "valor_parcela": round(valor_parcela, 2),
        "total": round(valor_parcela * quantidade, 2),
        "status": "Em andamento",
        "parcelas_pagas": 0
    }

    session.modified = True

    return redirect(url_for("detalhes_emprestimos"))


@app.route("/emprestimo/limpar", methods=["POST"])
def limpar_emprestimo():
    session.pop("emprestimo", None)
    return redirect(url_for("detalhes_emprestimos"))


@app.route("/relatorio", methods=["GET"])
def relatorio():
    emprestimo = session.get("emprestimo")

    if not emprestimo:
        return (
            "Nenhum empréstimo cadastrado para gerar o relatório.",
            404
        )

    parcelas = gerar_parcelas(emprestimo)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(
        190, 12,
        texto_pdf("CredMais - Relatório de Empréstimo"),
        ln=True,
        align="C"
    )

    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(
        190, 10,
        texto_pdf("Informações do empréstimo"),
        ln=True
    )

    pdf.set_font("Arial", size=11)

    informacoes = [
        ("Cliente", emprestimo["cliente"]),
        ("Valor do empréstimo", f"R$ {formatar_reais(emprestimo['valor'])}"),
        ("Valor total a pagar", f"R$ {formatar_reais(emprestimo['total'])}"),
        (
            "Quantidade de parcelas",
            str(emprestimo["quantidade_parcelas"])
        ),
        (
            "Valor de cada parcela",
            f"R$ {formatar_reais(emprestimo['valor_parcela'])}"
        ),
        ("Data da contratação", emprestimo["data"]),
        ("Status", emprestimo["status"])
    ]

    for titulo, valor in informacoes:
        pdf.cell(65, 9, texto_pdf(f"{titulo}:"))
        pdf.cell(125, 9, texto_pdf(valor), ln=True)

    pdf.ln(8)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 10, texto_pdf("Lista de parcelas"), ln=True)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(25, 9, texto_pdf("Parcela"), border=1)
    pdf.cell(45, 9, texto_pdf("Vencimento"), border=1)
    pdf.cell(55, 9, texto_pdf("Valor (R$)"), border=1)
    pdf.cell(65, 9, texto_pdf("Status"), border=1, ln=True)

    pdf.set_font("Arial", size=9)

    for parcela in parcelas:
        pdf.cell(25, 9, str(parcela["numero"]), border=1)
        pdf.cell(45, 9, parcela["vencimento"], border=1)
        pdf.cell(
            55, 9,
            formatar_reais(parcela["valor"]),
            border=1
        )
        pdf.cell(
            65, 9,
            texto_pdf(parcela["status"]),
            border=1,
            ln=True
        )

    pdf.ln(8)

    pdf.set_font("Arial", "I", 9)
    pdf.cell(
        190, 8,
        texto_pdf(
            f"Relatório gerado em "
            f"{datetime.now().strftime('%d/%m/%Y às %H:%M')}"
        ),
        ln=True,
        align="C"
    )

    conteudo_pdf = pdf.output(dest="S")

    if isinstance(conteudo_pdf, str):
        conteudo_pdf = conteudo_pdf.encode("latin-1")

    arquivo = BytesIO(bytes(conteudo_pdf))
    arquivo.seek(0)

    return send_file(
        arquivo,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="relatorio_emprestimo_credmais.pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)