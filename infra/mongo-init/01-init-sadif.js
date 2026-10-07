// Executado uma única vez, na primeira inicialização do volume do MongoDB.
// Cria as coleções do crawler (ver src/sadif/dataconfig/variables.json). Os bancos
// Modules, YaraRules e Clients são criados pelo próprio SADIF no primeiro uso.
const crawler = db.getSiblingDB("Crawler");
for (const collection of [
  "crawler_with_credential_onion",
  "crawler_without_credential_onion",
  "crawler_with_credential_web",
  "crawler_without_credential_web",
]) {
  if (!crawler.getCollectionNames().includes(collection)) {
    crawler.createCollection(collection);
  }
}
