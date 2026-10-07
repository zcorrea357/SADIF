rule InternalMonitoramentoDomino01
{
    meta:
        description = "Domino: servidor Lotus Domino exposto"
        client = "Internal"
        type = "Domino"
        author = "SADIF e2e fixtures"
    strings:
        $host = "mail.internal-corp.example/names.nsf" nocase
        $banner = "Domino Server" nocase
    condition:
        $host and $banner
}
