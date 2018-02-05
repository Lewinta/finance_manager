// Copyright (c) 2017, Soldeva, SRL and contributors
// For license information, please see license.txt

frappe.ui.form.on('Loan', {
	"setup": (frm) => frm.add_fetch("customer", "default_currency", "customer_currency"),
	"onload": (frm) => {
		// to filter some link fields
		frm.trigger("set_queries");

		if (["Approved", "Linked"].includes(frm.doc.status)) {
			frm.set_value("status", "Sanctioned");
		}

		// let's clear the prompts
		frappe.run_serially([
			() => frm.payment_entry_prompt = undefined,
			() => frm.add_fine_prompt = undefined,
			() => frm.clean_fine_prompt = undefined
		]);
		
		if (frm.doc.status == "Fully Disbursed") {
			frm.page.add_menu_item("Recuperado", () => {
				frm.set_value("status", "Recuperado");
				frm.save("Update");
			}, true);
		}

		if (frm.doc.status == "Recuperado") {
			frm.page.add_menu_item("Reanudar", () => {
				frm.set_value("status", "Fully Disbursed");
				frm.save("Update");
			}, true);
		}
	},
	"onload_post_render": (frm) => {
		frappe.db.get_value("Currency Exchange", {
			"from_currency": "USD",
			"to_currency": "DOP"
		}, "exchange_rate").then((data) => {
			frm.doc.exchange_rate = data.exchange_rate
		}, (exec) => {
			frappe.msgprint("Hubo un problema mientras se cargaba la tasa de conversion de\
				Dolar a Peso.<br>Favor de contactar su administrador de sistema!")
		});

	},
	"refresh": (frm) => {
		frm.doc._dev_hide = 0;
		frappe.db.get_value("FM Configuration", "FM Configuration", "developer_mode")
			.then((data) => {
				frm.doc._dev_hide = eval(data.developer_mode) ? 0 : 1;
			});

		$.map([
			"needs_to_refresh",
			"toggle_fields",
			"add_buttons",
			"beautify_repayment_table",
		], (event) => frm.trigger(event));
		
		frm.set_df_property("repayment_periods", "read_only", true);
	},
	"validate": (frm) => frm.trigger("setup"),
	"needs_to_refresh": (frm) => {
		// check if it's a new doc
		if (frm.is_new()) {
			return 0; // let's just ignore it
		}

		let opts = {
			"method": "frappe.client.get_value"
		};

		opts.args = {
			"doctype": frm.doctype,
			"filters": {
				"name": frm.docname,
			},
			"fieldname": ["modified"]
		};

		// check the last time it was modified in the DB
		// //Was causing issues commented by LV
		// frappe.call(opts).then((response) => {
		// 	if (response && doc)
		// 		frm.doc.modified != response.message.modified && frm.reload_doc();
		// });
	},
	"gross_loan_amount": (frm) => {
		let expense_rate_dec = flt(frm.doc.legal_expense_rate / 100.000);
		frm.set_value("loan_amount", frm.doc.gross_loan_amount * (expense_rate_dec +1.000));
	},
	"make_jv": (frm) => {
		frm.call("make_jv_entry", "args").then((response) => {
			let doc = response.message;

			doc && frappe.model.sync(doc);

			frappe.set_route(["Form", doc.doctype, doc.name]);
		}, (exec) => frappe.msgprint("¡Ooops... algo salió mal!"));
	},
	"mode_of_payment": (frm) => {

		// check to see if the mode of payment is set
		if ( ! frm.doc.mode_of_payment) {
			return 0; // let's just ignore it
		}

		let opts = {
			"method": "erpnext.accounts.doctype.sales_invoice.sales_invoice.get_bank_cash_account"
		};

		opts.args = {
			"mode_of_payment": frm.doc.mode_of_payment,
			"company": frm.doc.company
		};

		// ok, now we're ready to send the request
		frappe.call(opts).then((response) => {
			// set the response body to a local letiable
			let data = response.message;

			// let's set the value
			frm.set_value("payment_account", frm.doc.customer_currency == "DOP" ?
				data.account : data.account.replace("DOP", "USD"));
		}, (exec) => frappe.msgprint("¡Hubo un problema mientras se cargaban las cuentas!"));
	},
	"set_account_defaults": (frm) => {
		// this method fetch the default accounts from
		// the FM Configuration panel if it exists


		// the method that we're going to execute in the server
		let opts = {
			"method": "frappe.client.get"
		};

		// and the arguments that it requires
		opts.args = {
			"doctype": "FM Configuration",
			"name": "FM Configuration"
		};

		frappe.call(opts).then((response) => {

			// set the response body to a local letiable
			let conf = response.message;

			// set the response doc object to a local letiable
			let fields = [
				"mode_of_payment",
				"payment_account",
				"expenses_account",
				"customer_loan_account",
				"interest_income_account",
				"disbursement_account"
			];

			// set the values
			$.map(fields, (field) => {
				// check to see if the field has value

				let account = frm.doc.customer_currency != "DOP" ?
					conf[field].replace("DOP", "USD") : conf[field];

				// it has no value, then set it
				frm.set_value(field, account);
			});
		}, (exec) => frappe.msgprint("¡Hubo un problema mientras se cargaban las cuentas!"));
	},
	"loan_application": (frm) => {
		// exit the function and do nothing
		// if loan application is triggered but has not data
		if ( ! frm.doc.loan_application) {
			return 0; // let's just ignore it
		}

		let opts = {
			"method": "fm.finance_manager.doctype.loan.loan.get_loan_application"
		} 

		opts.args = {
			"loan_application": frm.doc.loan_application
		}
		
		frm.call(opts).then((response) => {
			let loan_application = response.message;

			// exit the callback if no data came from the SV
			if ( ! loan_application) {
				return 0; // let's just ignore it
			}

			$.map([
				"loan_type", 
				"loan_amount",
				"repayment_method",
				"monthly_repayment_amount",
				"repayment_periods",
				"rate_of_interest"
			], (field) => frm.set_value(field, loan_application[field]));
		}, () => frappe.msgprint("¡Hubo un problema mientras se carga la Solicitud de Prestamo!"));
	},
	"customer": (frm) =>  frm.trigger("set_account_defaults"),
	"repayment_method": (frm) => frm.trigger("toggle_fields"),
	"toggle_fields": (frm) => {
		frm.toggle_enable("monthly_repayment_amount", 
			frm.doc.repayment_method == "Repay Fixed Amount per Period");

		frm.toggle_enable("repayment_periods", 
			frm.doc.repayment_method == "Repay Over Number of Periods");

		frm.trigger("fix_table_header")
	},
	"clean_fines": (frm) => {

		fields = [{
			"fieldtype": "HTML",
			"options": "Se borraran las moras de todos los Pagares con estado PENDIENTE",
		}];

		let onsubmit = () => {

			frappe.confirm("¿Borrar todas las moras?", () => {

				let opts = {
					"method": "fm.utilities.clean_all_fines"
				} 

				opts.args = {
					"loan": frm.docname
				}

				frappe.call(opts).then((response) => {
					// let the user know that it was succesfully created
					frappe.show_alert(__("Mora eliminadas correctamente"), 9);

					// let's play a sound for the user
					frappe.utils.play_sound("submit");

					// clear the prompt
					frm.reload_doc();
				});
			}, () => frm.clean_fine_prompt.show());
		}

		// let's check if object is already set
		if (frm.clean_fine_prompt) {

			// it is set at this point
			// let's just make it visible
			frm.clean_fine_prompt.show()
		} else {

			// there was not object, so we need to create it
			frm.clean_fine_prompt = frappe.prompt(fields, onsubmit, __("Eliminar todas las Moras"), "Eliminar");
		}
	},
	"add_fines": (frm) => {
		fields = [{
			"fieldname": "repayment",
			"fieldtype": "Int",
			"label": __("Cuota"),
			"reqd": 1
		}, {
			"fieldname": "cb1",
			"fieldtype": "Column Break",
			"label": ""
		}, {
			"fieldname": "fine",
			"fieldtype": "Float",
			"label": "Mora",
			"description": "Ingresar monto con signo negativo para reducir mora.",
			"reqd": "1"
		} ];

		// finishes introducing the values
		let onsubmit = (data) => {

			frappe.confirm("¿Desea continuar?", () => {

				// method to be executed in the server
				let opts = {
					"method": "fm.utilities.add_fine"
				};

				opts.args = {
					"loan": frm.docname,
					"cuota": data.repayment,
					"mora": data.fine
				};

				frappe.call(opts).then((response) => {
					// let the user know that it was succesfully created
					frappe.show_alert(__("Mora agregada correctamente"), 9);

					// let's play a sound for the user
					frappe.utils.play_sound("submit");

					// clear the prompt
					frm.reload_doc();
				});
			}, () => frm.add_fine_prompt.show());
		}

		// let's check if object is already set
		if (frm.add_fine_prompt) {

			// it is set at this point
			// let's just make it visible
			frm.add_fine_prompt.show();
		} else {

			// there was not object, so we need to create it
			frm.add_fine_prompt = frappe.prompt(fields, onsubmit, __("Agregar Mora"), "Agregar");
		}
	},
	"add_buttons": (frm) => {
		if ( ! frm.is_new()) {
			frm.add_custom_button("Refrescar", () => frm.reload_doc());
		}

		// validate that the document is submitted
		if ( ! frm.doc.docstatus == 1) {
			return 0; // exit code is zero
		}


		frm.add_custom_button('Desembolso', () => {
			frappe.db.get_value("Journal Entry", {
				"loan": frm.docname,
				"docstatus": ["!=", 2]
			}, "name").then((data) => {
				frappe.set_route("List", "Journal Entry", {
					"loan": frm.docname,
					"es_un_pagare": "0"
				});
			}, () => frappe.throw("¡No se encontro ningún desembolso para este prestamo!"));
		}, "Ver");

		frm.add_custom_button(__('Payment Entry'), () => {
			frappe.set_route("List", "Journal Entry", {
				"loan": frm.docname,
				"es_un_pagare": "1"
			});
		}, "Ver");

		if (frappe.session.user == "Administrator" || true){
			frm.add_custom_button('Agregar', () => frm.trigger("add_fines"), "Mora");
			frm.add_custom_button('Borrar', () => frm.trigger("clean_fines"), "Mora");
		}

		if (["Partially Disbursed", "Sanctioned"].includes(frm.doc.status)) {
			frm.add_custom_button(__('Disbursement Entry'), () => frm.trigger("make_jv"), "Hacer")
		}

		if (frm.doc.status == "Fully Disbursed") {
			frm.add_custom_button('Entrada de Pago', () => frm.trigger("make_payment_entry"), "Hacer");
		}
		
		frm.add_custom_button('Poliza de Seguro', () => frm.trigger("insurance"), "Hacer");
		frm.page.set_inner_btn_group_as_primary("Hacer");
	},
	"set_queries": (frm) => {
		let root_types = {
			"interest_income_account": "Income",
			"expenses_account": "Income",
			"payment_account": "Asset",
			"customer_loan_account": "Asset"
		};

		let fields = [
			"interest_income_account", "expenses_account",
			"payment_account", "customer_loan_account"
		];

		$.map(fields, function(field) {
			frm.set_query(field, () => {
				return {
					"filters": {
						"company": frm.doc.company,
						"root_type": root_types[field],
						"is_group": 0
					}
				};
			});
		});

		frm.set_query("loan_application", () => {
			return {
				"filters": {
					"docstatus": 1,
					"status": "Approved",
					"status": ["!=", "Linked"]
				}
			};
		});
	},
	"fix_table_header": (frm) => {
		setTimeout(() => {
			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=fecha]")
			.css("width", "14%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=cuota]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=balance_capital]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=balance_interes]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=capital_acumulado]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=interes_acumulado]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=pagos_acumulados]")
			.css("width", "9%");

			$("[data-fieldname=repayment_schedule] \
				[data-fieldname=estado]")
			.css("width", "14%");

			$("[data-fieldname=repayment_schedule] \
				.close.btn-open-row").parent()
			.css("width", "5%");

			$("[data-fieldname=repayment_schedule] \
				.grid-heading-row .col.col-xs-1")
			.css("height", 60);

			$("[data-fieldname=repayment_schedule] \
				.grid-heading-row .col.col-xs-2")
			.css("height", 60);

			$("[data-fieldname=repayment_schedule] [data-fieldname=fecha] \
				.static-area.ellipsis:first")
			.html("<br>Fecha");

			$("[data-fieldname=repayment_schedule] [data-fieldname=cuota] \
				.static-area.ellipsis:first")
			.html("<br>Cuota");

			$("[data-fieldname=repayment_schedule] [data-fieldname=balance_capital] \
				.static-area.ellipsis:first")
			.html("Bal.<br>Capital");

			$("[data-fieldname=repayment_schedule] [data-fieldname=balance_interes] \
				.static-area.ellipsis:first")
			.html("Bal.<br>Interes");

			$("[data-fieldname=repayment_schedule] [data-fieldname=capital_acumulado] \
				.static-area.ellipsis:first")
			.html("Capital<br>Acum.");

			$("[data-fieldname=repayment_schedule] [data-fieldname=interes_acumulado] \
				.static-area.ellipsis:first")
			.html("Comision<br>Acum.");

			$("[data-fieldname=repayment_schedule] [data-fieldname=pagos_acumulados] \
				.static-area.ellipsis:first")
			.html("Pagos<br>Acum.");

			$("[data-fieldname=repayment_schedule] [data-fieldname=estado] \
				.static-area.ellipsis:first")
			.html("<br>Estado");
		});
	},
	"beautify_repayment_table": (frm) => {
		setTimeout(() => {

			// let's prepare the repayment table's apereance for the customer
			let fields = $("[data-fieldname=repayment_schedule] \
				[data-fieldname=estado] > .static-area.ellipsis");

			// ok, now let's iterate over map row
			$.map(fields, (value) => {

				let color = "grey";
				let field = $(value);

				// let's remove the previous css class
				clear_class(field);

				if ("SALDADA" == field.text()) {
					color = "green";
				} else if ("ABONO" == field.text()) {
					color = "blue";
				} else if ("PENDIENTE" == field.text()) {
					color = "orange";
				} else if ("VENCIDA" == field.text()) {
					color = "red";
				}
				
				field.addClass(__("indicator {0}", [color]));
			});
		});

		let clear_class = (field) => {
			$.map(["green", "blue", "orange", "red"], (css_class) => {
				field.removeClass(__("indicator {0}", [css_class]));
			});	
		}
	},
	"insurance": (frm) => {
		let today = frappe.datetime.get_today()

		let opts = {
			"method": "frappe.client.get_value"
		}

		opts.args = {
			"doctype": "Poliza de Seguro",
			"filters": {
				"loan": frm.doc.name,
				"docstatus": ["!=", "2"],
				"start_date": ["<=", today],
				"end_date": [">=", today]
			},
			"fieldname": ["name"]
		};

		frappe.call(opts).then((response) => {
			let data = response.message;
			if ( ! data) {
				frappe.new_doc("Poliza de Seguro", {
					"vehicle": frm.doc.asset,
					"loan": frm.docname
				});
			} else {
				frappe.set_route(["Form", "Poliza de Seguro", data.name])
			}
		});
	},
	"make_payment_entry": (frm) => {
		let read_only_discount = !!! frappe.user.has_role("Gerente de Operaciones");

		// let next_cuota = undefined
		let next_pagare = undefined;

		let found = false;
		let currency = frm.doc.customer_currency

		$.map(frm.doc.repayment_schedule, (value) => {

			// if there's no one found yet
			if ( ! found && value.estado != "SALDADA") {
				// means that this is the first one PENDING

				found = true; // set the flag to true
				next_pagare = value; // and set the value
			}
		});

		// set the fine amount if there is one
		let fine_amount = ! next_pagare.fine ? 0 : next_pagare.fine;
		let fine_discount = ! next_pagare.fine_discount ? 0 : next_pagare.fine_discount;
		let repayment_amount = ! next_pagare.cuota ? frm.doc.monthly_repayment_amount : next_pagare.cuota;

		let get_mode_of_payment_options = () => {
			return [
				{ "value": "Cash Entry", "label": "Efectivo" },
				{ "value": "Journal Entry", "label": "Asiento Contable" },
				{ "value": "Bank Entry", "label": "Transferencia" },
				{ "value": "Bank Entry", "label": "Cheque" },
				{ "value": "Bank Entry", "label": "Deposito Bancario" },
				{ "value": "Credit Card Entry", "label": "Tarjeta de Credito" },
				{ "value": "Debit Note", "label": "Nota de Debito" },
				{ "value": "Credit Note", "label": "Nota de Credito" },
			];
		};

		// these are the fields to be shown
		let fields = [{
			"fieldname": "paid_amount",
			"fieldtype": "Float",
			"label": "Monto Recibido (DOP)",
			"reqd": 1,
			"precision": 2,
			"default": next_pagare.monto_pendiente
		}, {
			"fieldname": "mode_of_payment",
			"fieldtype": "Select",
			"label": "Modo de Pago",
			"reqd": "1",
			"options": get_mode_of_payment_options(),
			"default": "Cash Entry",
		}, {
			"fieldname": "reference_name",
			"fieldtype": "Data",
			"label": "Referencia",
		}, {
			"fieldname": "reference_date",
			"fieldtype": "Date",
			"label": "Fecha de Referencia",
			"default": frappe.datetime.now_date()
		}, {
			"fieldname": "payment_section",
			"fieldtype": "Column Break"
		}, {
			"fieldname": "repayment_idx",
			"fieldtype": "Int",
			"label": __("Pagare No."),
			"read_only": 1,
			"default": next_pagare.idx
		}, {
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"label": "Fecha de Posteo",
			"default": frappe.datetime.get_today()
		}, {
			"fieldname": "has_gps",
			"label": "Agregar GPS",
			"fieldtype": "Check",
			"default": 0
		}, {
			"fieldname": "has_recuperacion",
			"label": "Agregar Recuperacion",
			"fieldtype": "Check",
			"default": 0
		}, {	
			"fieldname": "add_user_remarks",
			"label": "Agregar Notas",
			"fieldtype": "Check",
			"default": 0
		}, {	
			"fieldname": "validate_payment_entry",
			"label": "Validar Entrada de Pago",
			"fieldtype": "Check",
			"default": 1
		}, {
			"fieldname": "fine_section",
			"fieldtype": "Section Break"
		}, {
			"fieldname": "fine",
			"fieldtype": "Currency",
			"label": "Mora (DOP)",
			"precision": 2,
			"read_only": 1,
			"default": fine_amount ? fine_amount: 0.000
		}, {
			"fieldname": "discount_column",
			"fieldtype": "Column Break"
		}, {
			"fieldname": "fine_discount",
			"fieldtype": "Currency",
			"label": "Descuento a Mora (DOP)",
			"default": "0.000",
			"precision": 2,
			"default": fine_discount ? fine_discount: 0.000,
			"read_only": 1
		}, {
			"fieldname": "other_discounts",
			"fieldtype": "Float",
			"label": "Otros descuentos (DOP)",
			"default": "0.000",
			"precision": 2,
			"onchange": () => console.log("other_discounts changed")
		}, {
			"label": "Miscelaneos",
			"fieldname": "miscelaneos",
			"fieldtype": "Section Break",
		}, {
			"fieldname": "gps",
			"fieldtype": "Float",
			"label": "GPS (DOP)", 
			"default": "0.000",
			"description": "Debe ser considerado como parte del Monto Recibido",
			"precision": 2,
		}, {
			"fieldname": "expenses_column",
			"fieldtype": "Column Break",
		}, {
			"fieldname": "gastos_recuperacion",
			"fieldtype": "Float",
			"label": "Gastos  de Recuperacion (DOP)",
			"default": "0.000",
			"description": "Debe ser considerado como parte del Monto Recibido",
			"precision": 2,
		}, {
			"fieldtype": "Section Break"
		}, {
			"fieldname": "insurance_amount",
			"fieldtype": "Float",
			"label": __("Monto Seguro (DOP)"),
			"default": next_pagare.insurance || 0.000,
			"hidden": ! next_pagare.insurance || 0,
			"read_only": 1,
			"precision": 2,
		}, /*{
			"fieldname": "pending_insurance_amount",
			"fieldtype": "Currency",
			"label": __("Pendiente de Seguro (DOP)"),
			"read_only": 1,
			"precision": 2,
			"hidden": ! next_pagare.insurance || 0,
			"default": next_pagare.insurance || 0.000
		}, */
		{
			"fieldname": "repayment_section",
			"fieldtype": "Column Break"
		}, {
			"fieldname": "pending_amount",
			"fieldtype": "Currency",
			"label": "Monto del Pendiente (DOP)",
			"read_only": 1,
			"precision": 2,
			"default": next_pagare.monto_pendiente
		}, {
			"fieldname": "repayment_amount",
			"fieldtype": "Currency",
			"label": "Monto del Pagare (DOP)",
			"read_only": 1,
			"precision": 2,
			"default": repayment_amount
		},
		{
			"fieldname": "remarks_section",
			"fieldtype": "Section Break"
		},
		{
			"fieldname": "user_remark",
			"fieldtype": "Text",
			"label": "NOTAS DE USUARIO",
		}];

		// the callback to execute when user finishes introducing the values
		let onsubmit = (data) => {
			frappe.confirm("¿Desear crear una Entrada de Pago?", () => {

				// method to be executed in the server
				let opts = {
					"method": "fm.accounts.make_payment_entry"
				}

				$.extend(data, {
					"doctype": frm.doctype,
					"docname": frm.docname,
					"capital_amount": next_pagare.capital,
					"interest_amount": next_pagare.interes,
					"paid_amount": flt(data.paid_amount) + flt(data.fine_discount),
					"validate_payment_entry": data.validate_payment_entry? true: false
				});

				opts.args = { "opts": data };

				frappe.call(opts).then((response) => {
					let name = response.message;

					// let the user know that it was succesfully created
					frappe.show_alert("Entrada de pago creada", 9.000);

					// let's play a sound for the user
					frappe.utils.play_sound("submit");

					// clear the prompt
					frm.reload_doc();

					setTimeout(() => frappe.hide_msgprint(), 2500.000);
					
					if (name) {
						// let's show the user the new payment entry
						frappe.set_route("List", "Journal Entry", { 
							"loan": frm.docname,
							"es_un_pagare": "1"
						});
					}
				}, () => frappe.msgprint("¡Hubo un problema mientras se creaba la Entrada de Pago!"));
			}, () => frm.payment_entry_prompt.show());
		}

		// let's check if object is already set
		if (frm.payment_entry_prompt) {

			// it is set at this point
			// let's just make it visible
			frm.payment_entry_prompt.show()
		} else {

			// there was not object, so we need to create it
			frm.payment_entry_prompt = frappe.prompt(fields, onsubmit, __("Payment Entry"), "Submit");

			// default status for the wrapper
			frm.payment_entry_prompt.fields_dict.miscelaneos.wrapper.hide();
			frm.payment_entry_prompt.fields_dict.gps.$wrapper.hide();
			frm.payment_entry_prompt.fields_dict.gastos_recuperacion.$wrapper.hide();

			frm.payment_entry_prompt.fields_dict.reference_name.toggle(false);
			frm.payment_entry_prompt.fields_dict.reference_date.toggle(false);

			frm.payment_entry_prompt.fields_dict.user_remark.$input.css({ "height": "120px" });
			frm.payment_entry_prompt.fields_dict.remarks_section.wrapper.hide();


			// frm.payment_entry_prompt.fields_dict.fine_discount.$input.off();

			frm.payment_entry_prompt.fields_dict.fine_discount.change = (event) => {
				let fine_discount = flt(frm.payment_entry_prompt.get_value("fine_discount"));
				let pending_amount = flt(frm.payment_entry_prompt.get_value("pending_amount"));
			   
				frm.payment_entry_prompt.set_value("paid_amount", pending_amount - fine_discount);
			};
			frm.payment_entry_prompt.fields_dict.fine_discount.bind_change_event();

			frm.payment_entry_prompt.fields_dict.has_gps.change = (event) => {
				let checked = frm.payment_entry_prompt.get_value("has_gps");
				
				if (checked) {
				
					frm.payment_entry_prompt.set_value("gps", flt(frappe.boot.fm_configuration.gps_amount))
						.then(() => {
							let _gps = frm.payment_entry_prompt.get_value("gps");
							let _recuperacion =	frm.payment_entry_prompt.get_value("gastos_recuperacion");
							let _paid_amount = frm.payment_entry_prompt.get_value("paid_amount")
								+ frm.payment_entry_prompt.get_value("other_discounts");

							if( _gps + _recuperacion > _paid_amount){
								frm.payment_entry_prompt.set_value("paid_amount", _gps + _paid_amount)
							}
							
						});

					frm.payment_entry_prompt.fields_dict.gps.$wrapper.show();

					// if checked then let's also show the section break
					frm.payment_entry_prompt.fields_dict.miscelaneos.wrapper.show();

					
				} else {
					frm.payment_entry_prompt.fields_dict.gps.$wrapper.hide();

					// finally if there's no value in the other one
					if ( ! frm.payment_entry_prompt.get_value("has_recuperacion")) {
						frm.payment_entry_prompt.fields_dict.miscelaneos.wrapper.hide();
					}
					_gps = frm.payment_entry_prompt.get_value("gps");
					frm.payment_entry_prompt.set_value("gps", 0.000);
				}
			};
			frm.payment_entry_prompt.fields_dict.has_gps.bind_change_event();

			frm.payment_entry_prompt.fields_dict.has_recuperacion.change = (event) => {
				let checked = frm.payment_entry_prompt.get_value("has_recuperacion");
				
				if (checked) {

					frm.payment_entry_prompt.set_value("gastos_recuperacion", flt(frappe.boot.fm_configuration.recuperation_amount))
						.then(()=>{
						let _recuperacion =	frm.payment_entry_prompt.get_value("gastos_recuperacion");
						let _gps = frm.payment_entry_prompt.get_value("gps");
						let _paid_amount = frm.payment_entry_prompt.get_value("paid_amount")
							+ frm.payment_entry_prompt.get_value("other_discounts");

						if( _recuperacion + _gps > _paid_amount){
							frm.payment_entry_prompt.set_value("paid_amount", _recuperacion + _paid_amount)
						}
						
					});



					frm.payment_entry_prompt.fields_dict.gastos_recuperacion.$wrapper.show();

					// if checked then let's also show the section break
					frm.payment_entry_prompt.fields_dict.miscelaneos.wrapper.show();
					
				} else {
					frm.payment_entry_prompt.fields_dict.gastos_recuperacion.$wrapper.hide();

					// finally if there's no value in the other one
					if ( ! frm.payment_entry_prompt.get_value("has_gps")) {
						frm.payment_entry_prompt.fields_dict.miscelaneos.wrapper.hide();
					}

					_recuperacion = frm.payment_entry_prompt.get_value("gastos_recuperacion");
					frm.payment_entry_prompt.set_value("gastos_recuperacion", 0.000);
				} 
			};
			frm.payment_entry_prompt.fields_dict.has_recuperacion.bind_change_event();

			frm.payment_entry_prompt.fields_dict.insurance_amount.change = (event) => {
				let insurance_amount = frm.payment_entry_prompt.get_value("insurance_amount");
				
				if ( ! frm.doc.pending_insurance_amount) {
					frm.doc.pending_insurance_amount = frm.payment_entry_prompt.get_value("pending_insurance_amount");
				}
				
				if (insurance_amount < 0) {
					frm.payment_entry_prompt.set_value("insurance_amount", 0.000);
					frm.payment_entry_prompt.set_value("pending_insurance_amount", frm.doc.pending_insurance_amount);
					frappe.throw("¡Monto de Seguro invalido!");
				}

				if (insurance_amount > frm.doc.pending_insurance_amount) {
					frm.payment_entry_prompt.set_value("pending_insurance_amount", 0.000);
					frm.payment_entry_prompt.set_value("insurance_amount", frm.doc.pending_insurance_amount);
					frappe.throw("¡Monto de Seguro no puede ser mayor al establecido en la cuota!");
				}

				let new_pending_insurance_amount = frm.doc.pending_insurance_amount - insurance_amount;
				frm.payment_entry_prompt.set_value("pending_insurance_amount", new_pending_insurance_amount);
			};
			frm.payment_entry_prompt.fields_dict.insurance_amount.bind_change_event();

			frm.payment_entry_prompt.fields_dict.mode_of_payment.change = (event) => {
				let mode_of_payment = frm.payment_entry_prompt.get_value("mode_of_payment");
				
				if (["Credit Card Entry", "Bank Entry"].includes(mode_of_payment)) {
					// make them mandatory then
					frm.payment_entry_prompt.fields_dict.reference_name.df.reqd = true;
					frm.payment_entry_prompt.fields_dict.reference_date.df.reqd = true;

					frm.payment_entry_prompt.fields_dict.reference_name.toggle(true);
					frm.payment_entry_prompt.fields_dict.reference_date.toggle(true);
				} else {
					// make them non mandatory then
					frm.payment_entry_prompt.fields_dict.reference_name.df.reqd = false;
					frm.payment_entry_prompt.fields_dict.reference_date.df.reqd = false;
					
					frm.payment_entry_prompt.fields_dict.reference_name.toggle(false);
					frm.payment_entry_prompt.fields_dict.reference_date.toggle(false);
					

				}
			};
			frm.payment_entry_prompt.fields_dict.mode_of_payment.bind_change_event();

			frm.payment_entry_prompt.fields_dict.add_user_remarks.change = (event) => {
				let add_user_remarks = frm.payment_entry_prompt.get_value("add_user_remarks");

				if (add_user_remarks) {
					frm.payment_entry_prompt.fields_dict.remarks_section.wrapper.show();
				} else {
					frm.payment_entry_prompt.fields_dict.remarks_section.wrapper.hide();
				}
			};
			frm.payment_entry_prompt.fields_dict.add_user_remarks.bind_change_event();
			
			frm.payment_entry_prompt.set_value("gastos_recuperacion", 0.000);
			frm.payment_entry_prompt.set_value("gps", 0.000);
			frm.payment_entry_prompt.set_value("has_gps", 0.000);
			frm.payment_entry_prompt.set_value("has_recuperacion", 0.000);
			frm.payment_entry_prompt.set_value("add_user_remarks", 0.000);
		}
	}
});

frappe.ui.form.on('Tabla Amortizacion', {
	"voucher": (frm, cdt, cdn) => frappe.set_route(["List", "Journal Entry"], {
		"pagare": ["Like", __("%{0}%", [cdn])]
	}),
	"add_fine_discount": (frm, cdt, cdn) => new AddLoanDiscountPrompt(frm, cdt, cdn)
})

class AddLoanDiscountPrompt {
	constructor(frm, cdt, cdn) {
		this.frm = frm;
		this.cdt = cdt;
		this.cdn = cdn;

		this.init();
    }

	init() {
		let fields = [
			{"label": "Monto", "fieldname": "fine_discount", "fieldtype": "Float", "reqd": 1}
		];

		this.prompt = frappe.prompt(fields, (values) => this.process_data(values), "Descuento", "Agregar");
    }

	process_data(values) {
		// frappe.ui.form.close_grid_form();

		let args = {
			"doctype": this.cdt, "docname": this.cdn, 
			"fine_discount": values.fine_discount
		};

		this.frm.call("add_fine_discount_to_row", args)
			.fail(() => this.prompt && this.prompt.show())
		.done(() => this.frm.refresh_fields());
    }
}