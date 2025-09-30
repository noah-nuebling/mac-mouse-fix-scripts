"""
Archive GitHub Discussions to YAML
    See DiscussionsArchive/README.md
    Written mostly by Claude Code [Sep 2025]
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../shared'))

import mfgithub
import json
import ruamel.yaml
from datetime import datetime
import time
from pathlib import Path

# Output file paths
JSON_OUTPUT_PATH = "" # Set to emptystring if this is not needed || This is mostly useful for when the rate limit runs out – then we can still work on the json->yaml conversion [Sep 2025]
YAML_OUTPUT_PATH = "DiscussionsArchive/archive.yaml"

def fetch_all_discussions(api_key, owner, repo):

    # Design discussion:
    #   I'm extracting a pretty minimal amount of information for the archive [Sep 2025]
    #       E.g. we're omitting: 
    #           - Reactions (Not super important, and not very human-readable IIRC.)
    #           - closed status (only a handful of discussions are closed)
    #           - locked status (never locked a discussion) 
    #           - upvote count (Don't think that was used much)
    #           - urls (Can be inferred from username / discussion number)
    #           - updatedAt (Just seems not important)
    #       Pro: More human-readable?
    #       Con: Why not include more info in case we end up caring about it after all?
    #       Also see:
    #           - Available Discussion fields: https://docs.github.com/en/graphql/reference/objects#discussion
    #           - Available DiscussionComment fields: https://docs.github.com/en/graphql/reference/objects#discussioncomment
    #           - Available Actor fields: https://docs.github.com/en/graphql/reference/interfaces#actor
    
    all_discussions = []
    has_next_page = True
    cursor = None
    page = 1
    
    # Hardcode pagesizes
    #   Since we don't paginate, these page sizes need to be large enough to hold the largest number of comments/replies/... that occurs in our repo. This makes the rate-limits be used up crazy fast. [Sep 2025]
    pagesize_discussions = 50
    pagesize_labels = 5
    pagesize_comments = 25
    pagesize_replies = 20

    while has_next_page:
        print(f"📄 Fetching discussions page {page}...")
        
        # Build the query with pagination
        after_clause = f', after: "{cursor}"' if cursor else ''
        
        query = f"""
        repository(owner: "{owner}", name: "{repo}") {{
          discussions(first: {pagesize_discussions}{after_clause}) {{
            pageInfo {{
              hasNextPage
              endCursor
            }}
            nodes {{
              id
              number
              publishedAt
              author {{ login }}
              category {{ name }}
              labels(first: {pagesize_labels}) {{
                pageInfo {{ hasNextPage }}
                nodes {{ name }}
              }}
              answer {{ id }}
              title
              body
              comments(first: {pagesize_comments}) {{
                pageInfo {{ hasNextPage }}
                nodes {{
                  id
                  publishedAt
                  author {{ login }}
                  body
                  replies(first: {pagesize_replies}) {{
                    pageInfo {{ hasNextPage }}
                    nodes {{
                      id
                      publishedAt
                      author {{ login }}
                      body
                      replies(first: 1) {{
                        nodes {{ id }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        rateLimit {{
          used
          limit
          cost
          resetAt
        }}
        """
        
        result = mfgithub.github_graphql_request_query(api_key, query)

        if 'errors' in result:
            print(f"❌ GraphQL errors: {json.dumps(result['errors'], indent=2)}")
            raise Exception("GraphQL query failed")

        # Display rate limit info
        rate_limit = result['data']['rateLimit']
        print(f"   Rate limit: {rate_limit['used']}/{rate_limit['limit']} used up (cost for this query: {rate_limit['cost']}, resets at {rate_limit['resetAt']})")

        discussions_data = result['data']['repository']['discussions']
        discussions = discussions_data['nodes']

        print(f"   Found {len(discussions)} discussions on this page")
        
        # Validate pagination for nested lists
        for disc in discussions:
            disc_num = disc['number']

            # Check labels pagination
            if disc['labels']['pageInfo']['hasNextPage']:
                raise AssertionError(f"Discussion #{disc_num} has more than {pagesize_labels} labels! Needs pagination.")
            del disc['labels']['pageInfo']

            # Check comments pagination
            if disc['comments']['pageInfo']['hasNextPage']:
                raise AssertionError(f"Discussion #{disc_num} has more than {pagesize_comments} comments! Needs pagination.")
            del disc['comments']['pageInfo']

            # Check each comment's replies pagination
            for comment in disc['comments']['nodes']:
                if comment['replies']['pageInfo']['hasNextPage']:
                    raise AssertionError(f"Discussion #{disc_num}, comment {comment['id']} has more than {pagesize_replies} replies! Needs pagination.")
                del comment['replies']['pageInfo']

                # Check that replies don't have their own replies (nested replies)
                for reply in comment['replies']['nodes']:
                    if len(reply['replies']['nodes']) > 0:
                        raise AssertionError(f"Discussion #{disc_num} has nested replies (replies to replies)! This would be missing from archive.")
                    del reply['replies']

        all_discussions.extend(discussions)

        # Check if there are more pages
        page_info = discussions_data['pageInfo']
        del discussions_data['pageInfo'] # Delete `pageInfo` as not to clutter up the output.
        has_next_page = page_info['hasNextPage']
        cursor = page_info['endCursor']
        page += 1



        # Add delay between requests to avoid hitting secondary rate limits
        if has_next_page:
            time.sleep(1)
    
    print(f"\n✅ Fetched {len(all_discussions)} total discussions")
    return all_discussions


def main():
    
    api_key = os.getenv("GH_API_KEY")
    if not api_key:
        print("❌ Please set GH_API_KEY environment variable")
        exit(1)
    
    owner = "noah-nuebling"
    repo = "mac-mouse-fix"
    
    print(f"\n📚 Archiving discussions from {owner}/{repo}...\n")
    
    # Fetch all discussions
    objects = fetch_all_discussions(api_key, owner, repo)
    
    # Convert to JSON
    json_string = json.dumps(objects, indent=2, ensure_ascii=False)
    if True:
      # Remove windows line-endings (graphql seems to return them I think?)
      json_string = json_string.replace('\r\n', '\n')

    # Save raw JSON
    if JSON_OUTPUT_PATH:
        Path(JSON_OUTPUT_PATH).write_text(json_string)
        print(f"💾 Saved raw JSON to {JSON_OUTPUT_PATH}")

    # Save as YAML
    #   - We chose YAML over JSON since it can contain unescaped multiline strings which is more human-readable.
    #   - Use ruamel instead of PyYAML cause PyYAML couldn't apply '|' block-style consistently. See https://stackoverflow.com/questions/71836675/force-pyyaml-to-write-multiline-string-literals-regardless-of-string-content?noredirect=1#comment126957445_71836675
    with open(YAML_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        yaml = ruamel.yaml.YAML(typ='rt', pure=False) # typ='rt' is necessary to preserve dict-key order. PyYAMLs sort_keys doesn't seem to exist on ruamel.yaml [Sep 2025]
        yaml.default_flow_style = False
        yaml.allow_unicode = True
        def str_representer(dumper, data): # Use '|' block style for multiline strings.
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return     dumper.represent_scalar('tag:yaml.org,2002:str', data)
        yaml.representer.add_representer(str, str_representer)

        yaml.dump(objects, f)

    print(f"✅ Saved YAML archive to {YAML_OUTPUT_PATH}")

    # Log
    print(f"\n📊 Archive contains {len(objects)} discussions")


if __name__ == "__main__":
    main()