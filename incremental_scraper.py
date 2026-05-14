import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

BASE_URL = "http://ufcstats.com/statistics/events/completed?page="
CSV_PATH = "newufcfights.csv"


def get_page_html(page_number):
    url = BASE_URL + str(page_number)
    response = requests.get(url)
    return BeautifulSoup(response.content, "html.parser")


def get_last_loaded_event():
    df = pd.read_csv(CSV_PATH)
    return df["event"].iloc[0]


def get_existing_events():
    df = pd.read_csv(CSV_PATH)
    return set(df["event"].unique())


def scrape_new_events(existing_events):
    """Return list of (event_name, event_url) for events not yet in the CSV."""
    new_events = []
    page_number = 1

    while True:
        soup = get_page_html(page_number)
        event_links = soup.find_all("a", class_="b-link b-link_style_black")

        if not event_links:
            break

        found_existing = False
        for link in event_links:
            event_name = link.text.strip()
            event_url = link["href"]

            if event_name in existing_events:
                found_existing = True
                break

            new_events.append({"event_name": event_name, "event_url": event_url})

        if found_existing:
            break

        page_number += 1
        time.sleep(1)

    return new_events


def scrape_fights_for_event(event_name, event_url):
    response = requests.get(event_url)
    soup = BeautifulSoup(response.content, "html.parser")
    fight_table = soup.find("tbody")
    fights = []

    if fight_table:
        for row in fight_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 10:
                fights.append({
                    "event": event_name,
                    "fighter_1": cells[1].find_all("p")[0].text.strip(),
                    "fighter_2": cells[1].find_all("p")[1].text.strip(),
                    "weight": cells[6].text.strip(),
                    "result": cells[0].text.strip(),
                    "method": cells[7].text.strip(),
                    "round": cells[8].text.strip(),
                    "time": cells[9].text.strip(),
                })

    return fights


def main():
    existing_events = get_existing_events()
    last_event = next(iter(existing_events)) if existing_events else None
    print(f"Most recent event in CSV: {last_event}")

    new_events = scrape_new_events(existing_events)

    if not new_events:
        print("No new events found. CSV is already up to date.")
        return

    print(f"Found {len(new_events)} new event(s) to scrape:")
    for e in new_events:
        print(f"  - {e['event_name']}")

    new_fights = []
    for e in new_events:
        fights = scrape_fights_for_event(e["event_name"], e["event_url"])
        new_fights.extend(fights)
        print(f"Scraped {len(fights)} fights from: {e['event_name']}")
        time.sleep(1)

    if not new_fights:
        print("No fights found in new events.")
        return

    new_df = pd.DataFrame(new_fights)
    existing_df = pd.read_csv(CSV_PATH)

    # Prepend new fights (newest first) and save
    combined_df = pd.concat([new_df, existing_df], ignore_index=True)
    combined_df.to_csv(CSV_PATH, index=False)
    print(f"\nAdded {len(new_fights)} new fights to {CSV_PATH}.")


if __name__ == "__main__":
    main()
