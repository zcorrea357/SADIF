from pymongo import MongoClient


class MongoDBSaver:
    """
    Persists TheHive cases into a MongoDB collection.

    Parameters
    ----------
    mongo_uri : str | None
        MongoDB connection URI. Ignored when ``db_client`` is given.
    db_name : str
        Database name.
    collection_name : str
        Collection name.
    db_client : MongoClient | None
        An existing MongoClient to reuse instead of opening a new connection.

    Notes
    -----
    Cases are upserted by their TheHive ``_id``, so saving the same case twice updates
    the stored document instead of failing with ``DuplicateKeyError``.
    """

    def __init__(
        self,
        mongo_uri: str | None,
        db_name: str,
        collection_name: str,
        db_client: MongoClient | None = None,
    ):
        if db_client is None and not mongo_uri:
            msg = "mongo_uri or db_client must be provided"
            raise ValueError(msg)
        self.mongo_client = db_client if db_client is not None else MongoClient(mongo_uri)
        self.db = self.mongo_client[db_name]
        self.collection = self.db[collection_name]

    def save_cases(self, cases: list[dict]) -> int:
        """
        Save (upsert) the given cases.

        Parameters
        ----------
        cases : list[dict]
            Cases as returned by TheHive's API.

        Returns
        -------
        int
            Number of cases saved.
        """
        saved = 0
        for case in cases:
            if not isinstance(case, dict):
                msg = f"case should be a dict, got {type(case).__name__}"
                raise TypeError(msg)
            document = dict(case)  # não altera o dict do chamador (insert_one injeta _id)
            if document.get("_id") is not None:
                self.collection.replace_one({"_id": document["_id"]}, document, upsert=True)
            else:
                self.collection.insert_one(document)
            saved += 1
        return saved
