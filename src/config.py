"""Configurações centrais do sistema de acompanhamento de entregas Delly's."""

APP_NAME = "Controle de Entregas — Delly's Food Service"

# ---------------------------------------------------------------------------
# Modalidades (os três casos do sistema)
# ---------------------------------------------------------------------------
MODALIDADES = {
    "FLUVIAL_DP": {
        "label": "Fluvial · DP",
        "descricao": "Entregas fluviais operadas via DP",
        "veiculo_label": "Embarcação",
        "doc_label": "Identificação / Balsa",
        "icone": "🚢",
    },
    "FLUVIAL_RDW": {
        "label": "Fluvial · RDW",
        "descricao": "Entregas fluviais operadas via RDW",
        "veiculo_label": "Embarcação",
        "doc_label": "Identificação / Balsa",
        "icone": "⛴️",
    },
    "RODOVIARIO": {
        "label": "Rodoviário",
        "descricao": "Entregas rodoviárias (frota própria e terceiros)",
        "veiculo_label": "Veículo",
        "doc_label": "Placa",
        "icone": "🚚",
    },
}

MODALIDADE_PADRAO = "RODOVIARIO"


def modalidade_label(codigo: str) -> str:
    info = MODALIDADES.get(codigo, {})
    return f"{info.get('icone', '')} {info.get('label', codigo)}".strip()


# ---------------------------------------------------------------------------
# Status da CARGA (mesmos códigos usados na planilha original)
# ---------------------------------------------------------------------------
STATUS = {
    "P": "Programado",
    "T": "Em Trânsito",
    "E": "Entregue",
    "R": "Reagendado",
    "D": "Devolvido",
    "C": "Cancelado",
}

STATUS_CORES = {
    "P": "#4C78A8",
    "T": "#F58518",
    "E": "#54A24B",
    "R": "#B279A2",
    "D": "#E45756",
    "C": "#9C9C9C",
}

STATUS_POR_NOME = {v: k for k, v in STATUS.items()}

STATUS_CONCLUIDO = ("E",)
STATUS_IGNORADO = ("C",)

# ---------------------------------------------------------------------------
# Status da NOTA FISCAL (checkout por cliente)
# ---------------------------------------------------------------------------
STATUS_NOTA = {
    "P": "Pendente",
    "E": "Entregue",
    "R": "Reagendada",
    "D": "Devolvida",
    "C": "Cancelada",
}

STATUS_NOTA_CORES = {
    "P": "#9AA5B1",
    "E": "#54A24B",
    "R": "#F58518",
    "D": "#E45756",
    "C": "#6B7280",
}

# Nota resolvida = já passou pelo checkout (não está mais pendente)
STATUS_NOTA_RESOLVIDO = ("E", "R", "D", "C")

OCORRENCIAS = [
    "Sem ocorrência",
    "Cliente fechado",
    "Cliente ausente",
    "Recusa de mercadoria",
    "Avaria de produto",
    "Falta de mercadoria",
    "Divergência de pedido",
    "Problema de pagamento",
    "Endereço não localizado",
    "Atraso na carga",
    "Atraso no embarque",
    "Problema mecânico",
    "Problema de documentação",
    "Nível do rio / navegabilidade",
    "Outros",
]

TIPOS_TRANSPORTADORA = ["Proprio", "Terceiro", "Agregado"]

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

DIAS_SEMANA_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

UFS = ["AM", "BA", "DF", "ES", "MG", "SP", "PA", "RO", "RR", "AC", "AP"]

PRAZO_PADRAO_DIAS = 4
