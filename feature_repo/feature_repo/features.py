#feature_repo/feature_repo/features.py
from feast import Entity, FeatureView, Field
from feast.types import Int32, Float32, String
from feast.value_type import ValueType
from feast.infra.offline_stores.file_source import FileSource
from feast.data_source import PushSource
from datetime import timedelta

# Define an entity
realm = Entity(name="RealmId", join_keys=["RealmId"], value_type=ValueType.STRING)

# Define a dummy batch source with explicit timestamp_field
batch_source = FileSource(
    path="/dev/null",  
    timestamp_field="event_timestamp"  
)

# Define the PushSource for online writes
push_source = PushSource(
    name="fraud_features_push",
    batch_source=batch_source,
)

# Define the feature view
fraud_features = FeatureView(
    name="fraud_features",
    entities=[realm],
    ttl=timedelta(days=365),
    schema=[
        Field(name="UserId", dtype=Int32),
        Field(name="Account_number", dtype=String),
        Field(name="Date", dtype=String),
        Field(name="Amount", dtype=Float32),
        Field(name="Balance", dtype=Float32),
        Field(name="Narration", dtype=String),
        Field(name="Type", dtype=String),
    ],
    source=push_source,
)
