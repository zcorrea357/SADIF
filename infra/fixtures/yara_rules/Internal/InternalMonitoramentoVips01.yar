rule InternalMonitoramentoVips01
{
    meta:
        description = "VIP: diretoria executiva da Internal"
        client = "Internal"
        type = "Vips"
        author = "SADIF e2e fixtures"
    strings:
        $vip1 = "Mariana Albuquerque" nocase
        $vip2 = "Rodrigo Tavares" nocase
    condition:
        any of them
}
