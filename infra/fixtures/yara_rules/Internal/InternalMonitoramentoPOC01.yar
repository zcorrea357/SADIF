rule InternalMonitoramentoPOC01
{
    meta:
        description = "POC: ambiente de prova de conceito exposto"
        client = "Internal"
        type = "POC"
        author = "SADIF e2e fixtures"
    strings:
        $poc = "intranet-poc.internal-corp.example" nocase
    condition:
        $poc
}
