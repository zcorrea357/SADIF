rule UnknownCorpMonitoramentoVips01
{
    meta:
        description = "Cliente inexistente"
        client = "UnknownCorp"
        type = "Vips"
        author = "SADIF e2e fixtures"
    strings:
        $v = "Fernando Unknowncorp" nocase
    condition:
        $v
}
