rule AcmeMonitoramentoLeak99
{
    meta:
        description = "Regra com erro de sintaxe (condicao incompleta)"
    strings:
        $a = "acme-broken-token"
    condition:
        $a and
}
