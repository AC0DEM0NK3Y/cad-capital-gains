import requests
from datetime import date, timedelta, datetime
from click import ClickException


class ExchangeRate:
    min_date = date(2017, 1, 3)
    valet_obs_url = 'https://www.bankofcanada.ca/valet/observations'
    observations = "observations"
    currency_to = 'CAD'
    date = 'd'
    value = 'v'

    def __init__(self, currency_from, start_date, end_date):
        self._currency_from = currency_from
        self._start_date = start_date
        self._end_date = end_date

        if end_date < start_date:
            raise ClickException(
                "End date must be after start date")
        if start_date < self.min_date:
            raise ClickException(
                "Start date is before minimum date {}"
                .format(self.min_date.isoformat()))

        # Always move the start date back 7 days in case the start
        # date, end date, and all days in between are all weekends/holidays
        # where no exchange rate can be found
        start_date -= timedelta(days=7)

        # Query for all the exchange rates in the range specified, and
        # populates a dictionary that maps dates to exchange rates.
        params = {"start_date": start_date.isoformat(),
                  "end_date": end_date.isoformat()}
        forex_str = "FX{}{}".format(self._currency_from, self.currency_to)
        url = "{}/{}/json".format(self.valet_obs_url, forex_str)
        try:
            response = requests.get(url=url, params=params)
        except requests.ConnectionError as e:
            raise ClickException(
                "Error with internet connection to URL {} : {}".format(url, e))
        except requests.HTTPError as e:
            raise ClickException(
                "HTTP request for URL {} was unsuccessful : {}".format(url, e))
        except requests.exceptions.Timeout as e:
            raise ClickException(
                "Request timeout on URL {} : {}".format(url, e))
        except requests.exceptions.TooManyRedirects as e:
            raise ClickException(
                "URL {} was bad : {}".format(url, e))
        except requests.exceptions.RequestException as e:
            raise ClickException(
                "Catastrophic error with URL {} : {}".format(url, e))
        try:
            rates = response.json()[self.observations]
        except KeyError:
            raise ClickException(
                "No observations were found using currency {}"
                .format(self._currency_from))
        self._rates = dict()
        for day_rate in rates:
            date_str = day_rate[self.date]
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            rate = float(day_rate[forex_str][self.value])
            self._rates[date] = rate

    @property
    def currency_from(self):
        return self._currency_from

    @property
    def start_date(self):
        return self._start_date

    @property
    def end_date(self):
        return self._end_date

    def _get_closest_rate_for_day(self, date):
        """Gets the exchange rate for the closest
        preceeding date with a rate"""
        if date <= self.min_date:
            return None
        if date in self._rates:
            return self._rates[date]
        dates_preceeding = [d for d in self._rates if d < date]
        closest_date = min(dates_preceeding, key=lambda d: abs(d-date))
        return self._rates[closest_date]

    def get_rate(self, date):
        """Gets the exchange rate either:
        (1) for the day if an exchange rate exists for that day
        (2) for the closest preceeding day if an exchange rate does
            not exist for that day"""
        rate = self._get_closest_rate_for_day(date)
        if not rate:
            raise ClickException(
                "Unable to find exchange rate on {}".format(date))
        return rate