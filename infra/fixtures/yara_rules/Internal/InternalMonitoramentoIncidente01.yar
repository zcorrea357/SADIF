rule InternalMonitoramentoIncidente01
{
    meta:
        description = "Incidente: referencia a ticket de incidente interno"
        client = "Internal"
        type = "Incidente"
        author = "SADIF e2e fixtures"
    strings:
        $inc = /INC-INTERNAL-20[0-9]{2}-[0-9]{4}/
    condition:
        $inc
}
