odoo.define('currency.crypto_multisig_wallet_form', function (require) {
    "use strict";

    var core = require('web.core');
    var FormController = require('web.FormController');

    console.log("Defining CryptoMultisigWalletFormController");
    var CryptoMultisigWalletFormController = FormController.extend({
        custom_events: _.extend({}, FormController.prototype.custom_events, {
            'field_changed': '_onFieldChanged',
        }),

        init: function (parent, model, renderer, params) {
            this._super.apply(this, arguments);
            this.walletPages = [];
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._updateWalletPages();
            });
        },

        _updateWalletPages: function () {
            var self = this;
            var walletIds = this.model.get(this.handle).data.wallet_ids || [];
            var notebook = this.$el.find('#wallet_notebook');

            // Clear existing pages
            notebook.empty();

            // Add new pages dynamically
            _.each(walletIds, function (walletId, index) {
                var page = $('<page string="Wallet ' + (index + 1) + '"></page>');
                var field = $('<field name="wallet_ids" nolabel="1" widget="many2one" ' +
                    'domain="[(\'id\', \'=\', ' + walletId + ')]" ' +
                    'options="{\'no_create\': true, \'no_open\': true}"></field>');
                page.append(field);
                notebook.append(page);
            });

            // Update the DOM
            this.renderer._renderView();
        },

        _onFieldChanged: function (event) {
            if (event.data.changes.wallet_ids) {
                this._updateWalletPages();
            }
        },
    });

    core.form_widget_registry.add('crypto_multisig_wallet_form', CryptoMultisigWalletFormController);

    return {
        CryptoMultisigWalletFormController: CryptoMultisigWalletFormController,
    };
});