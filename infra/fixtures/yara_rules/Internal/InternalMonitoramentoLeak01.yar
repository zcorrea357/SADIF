rule InternalMonitoramentoLeak01
{
    meta:
        description = "Leak: credenciais corporativas vazadas"
        client = "Internal"
        type = "Leak"
        author = "SADIF e2e fixtures"
    strings:
        $dom = "@internal-corp.example" nocase
        $pwd = /(senha|password)\s*[:=]/ nocase
    condition:
        all of them
}
