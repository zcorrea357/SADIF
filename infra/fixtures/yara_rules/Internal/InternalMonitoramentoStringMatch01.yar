rule InternalMonitoramentoStringMatch01
{
    meta:
        description = "StringMatch: codinome de projeto confidencial"
        client = "Internal"
        type = "StringMatch"
        author = "SADIF e2e fixtures"
    strings:
        $s = "Projeto Aurora Confidencial" nocase
    condition:
        $s
}
