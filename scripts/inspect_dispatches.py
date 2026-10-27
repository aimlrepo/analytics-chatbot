import os
from google.cloud import bigquery

def inspect():
    project_id = os.getenv("GCP_CURATED_PROJECT_ID", "k-bicloud-curated-0001-p")
    client = bigquery.Client(project=project_id)
    table = client.get_table(f"{project_id}.l2l.dispatches_276")
    
    print("--- Fields in currentstatus (RECORD) ---")
    for field in table.schema:
        if field.name == "currentstatus":
            for subfield in field.fields:
                print(f"  • currentstatus.{subfield.name}: {subfield.field_type}")

    print("\n--- Testing SELECT query for site 276 ---")
    query = f"""
    SELECT 
        id,
        dispatchnumber,
        276 AS site,
        dispatchtype,
        currentstatus.description AS current_dispatchstatus_description,
        reported AS dispatch_reported,
        downtime,
        completed,
        open AS Open,
        tradecode,
        sigdowntime,
        machinecode,
        lineabbreviation,
        areacode,
        linecode,
        reasoncode,
        deleted
    FROM `{project_id}.l2l.dispatches_276`
    WHERE deleted IS NOT TRUE
    LIMIT 2
    """
    try:
        df = client.query(query).to_dataframe()
        print("Success! Sample row:")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Query error: {e}")

if __name__ == "__main__":
    inspect()
