This module adds the ability to track a number of Bitcoin and/or Lightning cryptocurrency wallets and address information. You can then associate them with companies, users, partners and other resources as necessary.

As well as helping to keep track of various addresses, there are few tools provided to act on them.

* A 'Create Payment' modal which can be activated from the 'Transactions' tab while viewing a particular Lightning Address.
* XPub analysis tab in the wallet view shows a few details about the address (i.e. to find/check XFP).

WARNING! Do not use in production! All fields are currently stored in plaintext in the database. Including details such as 'xpubs' and LSP macaroons, which should be considered sensitive.

REPEAT: DO NOT USE IN PRODUCTION. Early, insecure beta version. Only for local, test playground purposes with small amounts (at this time).

In future versions we will implement secure mechanisms according to modern best practices to ensure these fields are not stored or transmitted in plaintext.

Also, as it stands, this module evolved to encapsulate more functionality than it was originally intended to. I'll probably break this into multiple modules at some point; perhaps starting with one for the Bitcoin-related functionality and one for the Lightning-related functionality.

Other potential uses:

* On-chain workflows.
  * A vendor partner gives you a wallet address (`bc1q...`). This can be used to pay vendor bills (i.e. transmit PSBTs from company wallet). Or if more privacy is required, the vendor could provide a the `xpub...` address instead so it can derive a unique address for each payment.
  * You can assign wallet addresses (or xpubs) to customers, and use them to track payment histories.
  * Keeping track of transactions related to company-owned wallets, allowing for automating reconciliation workflows.
  * Chain analysis workflows. Find out where coins came from or went to.

* Off-chain workflows.
  * Track vendor's 'BOLT11' or 'BOLT12' addresses (for Lightning). Use them to make manual or scheduled payments (i.e. from your Lightning nodes).
  * When staff complete key tasks, they can be tipped automatically via a Lightning address associated with their user account.
  * Customers can be incentivised by micropayments to complete sales funnel goals.
