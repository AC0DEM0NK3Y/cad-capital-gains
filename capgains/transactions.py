class Transactions:
    """Holds a collection of transactions."""

    def __init__(self, transactions):
        self._transactions = list()
        self._tickers = dict()
        self._year_min = 9999
        self._year_max = 0
        for transaction in transactions:
            self.add_transaction(transaction)
        
        # Match journal transactions after loading
        self.match_journal_transactions()

    @property
    def transactions(self):
        """Return all the stored transactions."""
        return self._transactions

    @property
    def tickers(self):
        """Return all the unique tickers in this collection of transactions."""
        return sorted(self._tickers.keys())

    def __len__(self):
        return len(self.transactions)

    def __iter__(self):
        return iter(self.transactions)

    def __getitem__(self, x):
        return self.transactions[x]

    def add_transaction(self, transaction):
        """Add a transaction to the list of stored transactions."""
        self.transactions.append(transaction)

        ticker_refcount = self._tickers.get(transaction.ticker, 0)
        ticker_refcount += 1
        self._tickers[transaction.ticker] = ticker_refcount

        year = transaction.date.year
        self._year_min = min(self._year_min, year)
        self._year_max = max(self._year_max, year)

    def match_journal_transactions(self):
        """
        Ensure proper pairing of JOURNAL_IN and JOURNAL_OUT transactions.
        
        This method checks all transactions for journal entries and ensures
        that for each JOURNAL_OUT there is a corresponding JOURNAL_IN with 
        the same date and quantity. If an unpaired journal is found, it will
        attempt to infer the direction based on context.
        
        This is particularly important for Norbert's Gambit transactions
        where securities are journaled between USD and CAD accounts.
        """
        # First, identify all journal transactions
        journal_transactions = [t for t in self.transactions 
                               if 'JOURNAL' in t.action or t.action == 'JOURNAL']
        
        if not journal_transactions:
            return  # No journal transactions to match
            
        # Group journals by date and quantity
        from collections import defaultdict
        journal_groups = defaultdict(list)
        
        for transaction in journal_transactions:
            # Create a key based on date and quantity
            key = (transaction.date, float(transaction.qty))
            journal_groups[key].append(transaction)
        
        # Process each group of potential matches
        for (date, qty), group in journal_groups.items():
            # If we have exactly two transactions, verify they form a proper IN/OUT pair
            if len(group) == 2:
                # Check if we already have a correctly marked IN/OUT pair
                actions = set(t.action for t in group)
                if 'JOURNAL_IN' in actions and 'JOURNAL_OUT' in actions:
                    continue  # Already correctly paired
                    
                # If both are marked as generic JOURNAL, determine direction
                if all(t.action == 'JOURNAL' for t in group):
                    # Sort by currency - typically USD is OUT, CAD is IN for Norbert's Gambit
                    sorted_group = sorted(group, key=lambda t: t.currency)
                    
                    # Check original text if available
                    for t in sorted_group:
                        original_text = getattr(t, '_original_text', '')
                        if original_text:
                            if 'Transfer Out' in original_text or 'Transferred Out' in original_text:
                                t._action = 'JOURNAL_OUT'
                            elif 'Transfer In' in original_text or 'Transferred In' in original_text:
                                t._action = 'JOURNAL_IN'
                    
                    # If we still don't have direction, use currency as a heuristic
                    in_tx = None
                    out_tx = None
                    
                    for t in sorted_group:
                        if t.action == 'JOURNAL':  # Still not assigned
                            if in_tx is None and t.currency == 'CAD':
                                in_tx = t
                                t._action = 'JOURNAL_IN'
                            elif out_tx is None:  # First non-CAD or remaining transaction
                                out_tx = t
                                t._action = 'JOURNAL_OUT'
            
            # For single journals without a pair, try to infer direction
            elif len(group) == 1:
                transaction = group[0]
                if transaction.action == 'JOURNAL':  # Not yet assigned
                    original_text = getattr(transaction, '_original_text', '')
                    if original_text:
                        if 'Transfer Out' in original_text or 'Transferred Out' in original_text:
                            transaction._action = 'JOURNAL_OUT'
                        elif 'Transfer In' in original_text or 'Transferred In' in original_text:
                            transaction._action = 'JOURNAL_IN'
                    else:
                        # Use currency as heuristic
                        if transaction.currency == 'CAD':
                            transaction._action = 'JOURNAL_IN'
                        else:
                            transaction._action = 'JOURNAL_OUT'
            
            # For 3+ journals with same date/qty (unusual), use text or currency
            else:
                for transaction in group:
                    if transaction.action == 'JOURNAL':  # Not yet assigned
                        original_text = getattr(transaction, '_original_text', '')
                        if original_text:
                            if 'Transfer Out' in original_text or 'Transferred Out' in original_text:
                                transaction._action = 'JOURNAL_OUT'
                            elif 'Transfer In' in original_text or 'Transferred In' in original_text:
                                transaction._action = 'JOURNAL_IN'
                        else:
                            # Use currency as heuristic
                            if transaction.currency == 'CAD':
                                transaction._action = 'JOURNAL_IN'
                            else:
                                transaction._action = 'JOURNAL_OUT'

    def filter_by(
        self,
        tickers=None,
        year=None,
        max_year=None,
        action=None,
        superficial_loss=None
    ):
        """Filter the list of stored transactions on certain parameters (such
        as ticker, year, etc) and return only the transactions that match the
        requested parameters."""

        def lambda_filter(t):
            keep = True
            if tickers:
                keep &= (t.ticker in tickers)
            if year:
                keep &= (t.date.year == year)
            if max_year:
                keep &= (t.date.year <= max_year)
            if action:
                keep &= (t.action == action)
            if superficial_loss is not None:
                # superficial_loss can be set to False, so need to explicitly
                # check that it is not set to None
                keep &= (t.superficial_loss == superficial_loss)
            return keep

        filtered_transactions = Transactions(filter(lambda_filter, self.transactions))
        return filtered_transactions

    @property
    def year_min(self):
        return self._year_min

    @property
    def year_max(self):
        return self._year_max
