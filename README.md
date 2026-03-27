# Leetcode-Discussion-LLM

"""
1. Process link -> user will pass a link in post request(either topic id,or complete link)
    Check if already processed or not
    if not run the entire pipeline(will also save data) -> also return data in json format

2. Admin Panel(buttons need to identified)
    - Get new posts
        -- short posts
            Using this will fetch all posts
            return new posts and new updated posts(counts of each)

    - Transform posts
        - TRansform all posts
        - Transform updated posts

    - Filter unprocessed posts
        - filter all
        - filter new/updated

    - Processing using LLM/AI
        - Filter by COlumn(company ,updated at, is interviewd or not)
            - Process all
            - Process only new

3.  Dashboard
    - Search/FIlter/Sort  (COmpany name)
        -FIlter AI processed posts
    - Mood indicator
    
    TODOS
    1. better filters by using  column names and values
    2. Making code modular and reusable
    3. Mood Indicator
    4. Add testing
"""