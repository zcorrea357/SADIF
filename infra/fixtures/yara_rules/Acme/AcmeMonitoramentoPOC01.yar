rule AcmeMonitoramentoPOC01
{
    meta:
        description = "POC: homologacao exposta"
        client = "Acme"
        type = "POC"
        author = "SADIF e2e fixtures"
    strings:
        $poc = "staging-poc.acme-bank.example" nocase
    condition:
        $poc
}
