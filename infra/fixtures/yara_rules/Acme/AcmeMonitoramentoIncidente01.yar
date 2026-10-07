rule AcmeMonitoramentoIncidente01
{
    meta:
        description = "Incidente: ticket de incidente Acme"
        client = "Acme"
        type = "Incidente"
        author = "SADIF e2e fixtures"
    strings:
        $inc = /INC-ACME-20[0-9]{2}-[0-9]{4}/
    condition:
        $inc
}
