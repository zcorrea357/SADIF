rule AcmeMonitoramentoVips01
{
    meta:
        description = "VIP: conselho da Acme"
        client = "Acme"
        type = "Vips"
        author = "SADIF e2e fixtures"
    strings:
        $vip1 = "Beatriz Montenegro" nocase
        $vip2 = "Otavio Pradella" nocase
    condition:
        any of them
}
