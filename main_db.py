from transformation.filter_data_db import FilterDB
from extraction.get_discussion_details_db import DiscussionDB
from setup_database.setup_db import create_tables


# Ensure tables exist before running
# create_tables()

f = FilterDB(keywords=["google"], company_name="google")
f.transform()

f.company_filter_data()
f.save_company_data()


diss = DiscussionDB("google")
diss.get_all_discussions()
diss.save_data()
