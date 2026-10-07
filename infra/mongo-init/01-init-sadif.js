// Executado uma única vez, na primeira inicialização do volume do MongoDB.
// Cria os bancos usados pelo SADIF (ver src/sadif/dataconfig/variables.json).
const databases = ["Modules", "YaraRules", "Clients", "Crawler"];

for (const name of databases) {
  const database = db.getSiblingDB(name);
  if (!database.getCollectionNames().includes("sadif_meta")) {
    database.createCollection("sadif_meta");
    database.getCollection("sadif_meta").insertOne({ createdBy: "infra/mongo-init", createdAt: new Date() });
  }
}

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
