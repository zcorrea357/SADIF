rule AcmeMonitoramentoStringMatch01
{
    meta:
        description = "StringMatch: operacao sigilosa"
        client = "Acme"
        type = "StringMatch"
        author = "SADIF e2e fixtures"
    strings:
        $s = "Operacao Falcao Acme" nocase
    condition:
        $s
}
