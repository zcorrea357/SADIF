rule AcmeMonitoramentoDomino01
{
    meta:
        description = "Domino: webmail Domino da Acme"
        client = "Acme"
        type = "Domino"
        author = "SADIF e2e fixtures"
    strings:
        $host = "webmail.acme-bank.example/names.nsf" nocase
    condition:
        $host
}
