from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

BASE_URL = "http://www.ufcstats.com/statistics/events/completed?page=all"


class UFCScraper:
    def __init__(self, csv_path="newufcfights.csv"):
        self.csv_path = csv_path

    def _get_soup(self, page, url):
        page.goto(url, wait_until="networkidle")
        return BeautifulSoup(page.content(), "html.parser")

    def get_existing_events(self):
        df = pd.read_csv(self.csv_path)
        return set(df["event"].unique())

    def get_most_recent_event(self):
        df = pd.read_csv(self.csv_path)
        return df["event"].iloc[0]

    def scrape_new_events(self, page, existing_events):
        """Return list of (event_name, event_url) for events not yet in the CSV."""
        new_events = []
        soup = self._get_soup(page, BASE_URL)
        event_links = soup.find_all("a", class_="b-link b-link_style_black")

        for link in event_links:
            event_name = link.text.strip()
            event_url = link["href"]

            if event_name in existing_events:
                break

            new_events.append({"event_name": event_name, "event_url": event_url})

        return new_events

    def scrape_fights_for_event(self, page, event_name, event_url):
        soup = self._get_soup(page, event_url)
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

    def run(self):
        """Scrape new events and prepend them to the CSV. Returns a result summary dict."""
        existing_events = self.get_existing_events()
        print(f"Most recent event in CSV: {self.get_most_recent_event()}")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            new_events = self.scrape_new_events(page, existing_events)

            if not new_events:
                print("No new events found. CSV is already up to date.")
                browser.close()
                return {"new_events": 0, "new_fights": 0, "events": []}

            print(f"Found {len(new_events)} new event(s) to scrape:")
            for e in new_events:
                print(f"  - {e['event_name']}")

            new_fights = []
            scraped_events = []
            for e in new_events:
                fights = self.scrape_fights_for_event(page, e["event_name"], e["event_url"])
                new_fights.extend(fights)
                scraped_events.append({"name": e["event_name"], "fights": len(fights)})
                print(f"Scraped {len(fights)} fights from: {e['event_name']}")

            browser.close()

        if not new_fights:
            print("No fights found in new events.")
            return {"new_events": len(new_events), "new_fights": 0, "events": scraped_events}

        new_df = pd.DataFrame(new_fights)
        existing_df = pd.read_csv(self.csv_path)
        combined_df = pd.concat([new_df, existing_df], ignore_index=True)
        combined_df.to_csv(self.csv_path, index=False)
        print(f"\nAdded {len(new_fights)} new fights to {self.csv_path}.")

        return {
            "new_events": len(new_events),
            "new_fights": len(new_fights),
            "events": scraped_events,
        }


if __name__ == "__main__":
    UFCScraper().run()
