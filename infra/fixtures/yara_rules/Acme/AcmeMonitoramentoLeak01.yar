rule AcmeMonitoramentoLeak01
{
    meta:
        description = "Leak: credenciais de clientes Acme"
        client = "Acme"
        type = "Leak"
        author = "SADIF e2e fixtures"
    strings:
        $dom = "@acme-bank.example" nocase
        $pwd = /(senha|password)\s*[:=]/ nocase
    condition:
        all of them
}
