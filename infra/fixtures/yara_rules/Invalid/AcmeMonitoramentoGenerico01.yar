rule AcmeMonitoramentoGenerico01
{
    meta:
        description = "Tipo de regra inexistente"
        client = "Acme"
        type = "Generico"
        author = "SADIF e2e fixtures"
    strings:
        $g = "acme-generico-token"
    condition:
        $g
}
