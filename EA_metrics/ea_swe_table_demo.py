from bs4 import BeautifulSoup
import requests
from requests.exceptions import HTTPError
import time


APP_USERNAME = 'merge'
APP_PASSWORD = 'H3@lthp@rtn3rsP@C5'

sess = requests.Session()

try:
    login_url = 'https://mergeeasec/eaweb/login'
    r = sess.get(login_url, verify=False)

    # Raise an error if we get an "erorr" http status (e.g. 404)
    r.raise_for_status()


    # Parse content and get the hidden _csrf token
    soup=BeautifulSoup(r.content)
    csrfToken = soup.find("input",{"name":"_csrf"})['value']

    # Contruct login form submission payload
    payload = {
        'username' : APP_USERNAME,
        'password':APP_PASSWORD,
        'ldapDomain':'1',       # Assume that 'healthpartners.int' is the only option other than Local
        '_csrf': csrfToken
    }
except HTTPError as http_err:
    print(f'HTTP error occurred on login: {http_err}')
    exit()
except Exception as err:
    print(f'Other error occurred: {err}')
    exit()

try:
    post = sess.post(login_url, data=payload, verify=False)
    post.raise_for_status
except HTTPError as http_err:
    print(f'HTTP error occurred: {http_err}')
    exit()
except Exception as err:
    print(f'Other error occurred: {err}')
    exit()

current_unix_timestamp = int(time.time()*1000)

# Need to run this next
#url2 = 'https://mergeeasec/eaweb/monitoring/scheduledwork/getresponseobject'
#r2 = sess.get(url2, verify=False)

# Then this
execute_jquery_url = f'https://mergeeasec/eaweb/monitoring/scheduledwork/getsummaryresult?componentName=&taskName=&status=&_filterByGroupFlag=on&_actionGroupsFlag=on&groupIdentifier=&selectedAction=&singleCheckedItem=&nextAttemptDate=03%2F23%2F2022&nextAttemptTime=13%3A50&_csrf={csrfToken}'
jquery_response = sess.get(execute_jquery_url, verify=False)

# Note sure of the significance of the "draw=" argument to the function here. The page makes two calls with the value set to both 1 and 2. But setting it to 0 or ommitting it also seems to generate the same results.
get_jquery_result_url = f'https://mergeeasec/eaweb/monitoring/scheduledwork/getsummarypaginationresults?draw=0&columns%5B0%5D.data=Select&columns%5B0%5D.name=&columns%5B0%5D.searchable=true&columns%5B0%5D.orderable=false&columns%5B0%5D.search.value=&columns%5B0%5D.search.regex=false&columns%5B1%5D.data=componentName&columns%5B1%5D.name=&columns%5B1%5D.searchable=true&columns%5B1%5D.orderable=true&columns%5B1%5D.search.value=&columns%5B1%5D.search.regex=false&columns%5B2%5D.data=taskName&columns%5B2%5D.name=&columns%5B2%5D.searchable=true&columns%5B2%5D.orderable=true&columns%5B2%5D.search.value=&columns%5B2%5D.search.regex=false&columns%5B3%5D.data=groupIdentifier&columns%5B3%5D.name=&columns%5B3%5D.searchable=true&columns%5B3%5D.orderable=true&columns%5B3%5D.search.value=&columns%5B3%5D.search.regex=false&columns%5B4%5D.data=status&columns%5B4%5D.name=&columns%5B4%5D.searchable=true&columns%5B4%5D.orderable=true&columns%5B4%5D.search.value=&columns%5B4%5D.search.regex=false&columns%5B5%5D.data=count&columns%5B5%5D.name=&columns%5B5%5D.searchable=true&columns%5B5%5D.orderable=false&columns%5B5%5D.search.value=&columns%5B5%5D.search.regex=false&order%5B0%5D.column=1&order%5B0%5D.dir=asc&start=0&length=50&search.value=&search.regex=false&_={current_unix_timestamp}'
get_jquery_result_response = sess.get(get_jquery_result_url, verify=False)
json_response = get_jquery_result_response.json()

# Print the important data out from the "data" item in the json response
for data_item in json_response['data']:
    print(f'{data_item["componentName"]} - {data_item["taskName"]} - {data_item["status"]} - {data_item["count"]}') 

#Overall totals here. Probably not needed
get_summary_status_count_url = 'https://mergeeasec/eaweb/monitoring/scheduledwork/getsummarystatuscount'
get_summary_status_count_result = sess.get(get_summary_status_count_url, verify=False)


