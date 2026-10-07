rule AcmeMonitoramentoVips01
{
    meta:
        description = "Duplicata de AcmeMonitoramentoVips01 (conteudo alternativo)"
        client = "Acme"
        type = "Vips"
        author = "SADIF e2e fixtures"
    strings:
        $vip1 = "Beatriz Duplicada" nocase
    condition:
        $vip1
}
