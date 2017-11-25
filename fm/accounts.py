# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
import fm.api

from frappe import _
from datetime import datetime
from fm.api import *
from frappe.utils import flt

from fm.finance_manager.doctype.loan.loan import get_monthly_repayment_amount

def submit_journal(doc, event):
	if doc.loan and not doc.es_un_pagare:

		# load the loan from the database
		loan = frappe.get_doc("Loan", doc.loan)

		curex = frappe.get_doc("Currency Exchange", 
			{"from_currency": "USD", "to_currency": "DOP"})

		exchange_rate = curex.exchange_rate

		if loan.customer_currency == "DOP":
			exchange_rate = 1.000

		if not round(loan.total_payment) == round(doc.total_debit / exchange_rate):
			frappe.throw("El monto desembolsado difiere del monto del prestamo!")

		# call the update status function 
		loan.update_disbursement_status()

		# update the database
		loan.db_update()
	elif doc.loan and doc.es_un_pagare and doc.get("create_jv"):
		
		#Let's create a purchase Invoice
		if flt(doc.gps):
			fm.api.create_purchase_invoice( doc.gps, "GPS", doc.name)
		
		if flt(doc.gastos_recuperacion):
			fm.api.create_purchase_invoice( doc.gastos_recuperacion, "Recuperacion", doc.name)

		#Let's apply the payment to the Loan
		row = fm.api.next_repayment(doc.loan)
		capital = row.capital
		interes = row.interes
		# make_payment_entry("Loan", doc.loan, doc.amount_paid, capital, interes, doc.fine, doc.fine_discount, doc.insurance_amount, False)

		make_payment_entry(doctype="Loan",
			docname=doc.loan,
			paid_amount=doc.amount_paid,
			capital_amount=capital,
			interest_amount=interes,
			fine=doc.fine,
			fine_discount=doc.fine_discount,
			insurance=doc.insurance_amount,
			create_jv=False
		)

		# Let's Update the status if necessary
		loan = frappe.get_doc("Loan", doc.loan)
		# call the update status function
		loan.update_disbursement_status()
		#update the database
		loan.db_update() 

def cancel_journal(doc, event):
	if not doc.loan:
		return 0.000 # exit code is zero

	#Let's check if it has any linked Purchase Invoice 
	pinv_list = frappe.get_list("Purchase Invoice", { "linked_doc": doc.name })

	for current in pinv_list:
		pinv = frappe.get_doc("Purchase Invoice", current.name)

		if pinv.docstatus == 1:
			pinv.cancel()
			
		pinv.delete()

	filters = { 
		"loan": doc.loan,
		"es_un_pagare": "1" 
	}

	if not doc.es_un_pagare:

		if frappe.get_list("Journal Entry", filters):
			frappe.throw("No puede cancelar este desembolso con pagares hechos!")
	
		# load the loan from the database
		loan = frappe.get_doc("Loan", doc.loan)

		# call the update status function
		loan.update_disbursement_status()

		# update the database
		loan.db_update()

		return 0.000 # to exit the function
	 		
	else: update_repayment_amount(doc)
	
def update_repayment_amount(doc):

	loan = frappe.get_doc("Loan", doc.loan)

	# load the repayment to work it
	row = fm.api.get_repayment(loan, doc.pagare)

	if not row:
		frappe.throw("No se encontro ningun pagare asociado con esta Entrada de Pago.<br>\
			Es posible que se haya marcado como un pagare sin tener alguno asociado!")

	paid_amount = 0.000
	filters = { "pagare": row.name, "name": ["!=", doc.name], "docstatus": "1" }

	# let's see how much the customer has paid so far for this repayment
	for journal in frappe.get_list("Journal Entry", filters, "total_amount"):
		paid_amount += journal.total_amount
	
	# let see if we're canceling the jv
	if doc.docstatus == 2.000:

		interest_on_loans = frappe.db.get_single_value("FM Configuration", "interest_on_loans")
		interest_on_loans = interest_on_loans if loan.customer_currency == "DOP" \
			else interest_on_loans.replace("DOP", "USD")

		row.capital = fm.api.get_paid_amount(loan.customer_loan_account, doc.name, "capital") + row.capital
		row.interes = fm.api.get_paid_amount(loan.customer_loan_account, doc.name, "interes") + row.interes
		
		row.fine = fm.api.get_paid_amount(interest_on_loans, doc.name, "fine") + row.fine
		row.insurance = fm.api.get_paid_amount(loan.customer_loan_account, doc.name, "insurance") + row.insurance

		# let's make sure we update the status to the corresponding
		# row in the insurance doc
		fm.api.update_insurance_status("PENDIENTE", row.insurance_doc)

	# duty will be what the customer has to pay for this repayment
	duty = flt(row.cuota) + flt(row.fine) + row.insurance

	# then, the outstanding amount will be the 
	# duty less what he's paid so far
	row.monto_pendiente = duty - paid_amount

	# pass the latest paid amount so that it can update the loan status
	# with the realtime data that is out of date when this is run 

	# update the status of the repayment
	row.update_status()

	# save to the database
	row.db_update()

	loan.update_disbursement_status()
	loan.db_update()

def get_repayment_details(self):

	# validate that the interest type is simple
	if self.interest_type == "Simple":
		return get_simple_repayment_details(self)

	elif self.interest_type == "Composite":
		return get_compound_repayment_details(self)		

def get_simple_repayment_details(self):
	# if there's not rate set
	if not self.rate_of_interest: 	
		# now let's fetch from the DB the default rate for interest simple
		self.rate_of_interest = frappe.db.get_single_value("FM Configuration", "simple_rate_of_interest")

	# convert the rate of interest to decimal
	self.rate = flt(self.rate_of_interest) / 100.000

	# total interest using the simple interest formula
	self.total_payable_interest = self.loan_amount * self.rate * self.repayment_periods

	# calculate the monthly interest
	self.monthly_interest = flt(self.loan_amount * self.rate)

	# calculate the monthly capital
	self.monthly_capital = flt(self.loan_amount) / flt(self.repayment_periods)

	# get the monthly repayment amount
	self.monthly_repayment_amount = self.monthly_interest + self.monthly_capital

	# calculate the total payment
	self.total_payable_amount = self.loan_amount + self.total_payable_interest

def get_compound_repayment_details(self):
	# if there's not rate set
	if not self.rate_of_interest: 
		# now let's fetch from the DB the default rate for interest compound
		self.rate_of_interest = frappe.db.get_single_value("FM Configuration", "composite_rate_of_interest")
	
	if self.repayment_method == "Repay Over Number of Periods":
		self.repayment_amount = get_monthly_repayment_amount(
				self.interest_type,
				self.repayment_method, 
				self.loan_amount, 
				self.rate_of_interest,
				self.repayment_periods
			)

	self.calculate_payable_amount()

def make_simple_repayment_schedule(self):
	from fm.api import from_en_to_es
	
	# let's get the loan details
	get_repayment_details(self)
	
	# let's clear the table
	self.repayment_schedule = []

	# set defaults for this variables
	capital_balance = self.loan_amount
	interest_balance = self.total_payable_interest

	pagos_acumulados = interes_acumulado = 0.000
	capital_acumulado = 0.000

	
	payment_date = self.get("disbursement_date") or self.get("posting_date")

	# map the values from the old variables
	self.total_payment = self.total_payable_amount
	self.total_interest_payable = self.total_payable_interest

	# fetch from the db the maximun pending amount for a loan
	maximum_pending_amount = frappe.db.get_single_value("FM Configuration", "maximum_pending_amount")

	# ok, now let's add the records to the table
	while(capital_balance > flt(maximum_pending_amount)):

		monthly_repayment_amount = self.monthly_repayment_amount

		cuota =  round(self.monthly_capital + self.monthly_interest)
			
		capital_balance -= round(self.monthly_capital)
		interest_balance -= cuota - round(self.monthly_capital)
		pagos_acumulados += round(monthly_repayment_amount)
		interes_acumulado += cuota - round(self.monthly_capital)
		capital_acumulado += round(self.monthly_capital)

		# start running the dates
		payment_date = frappe.utils.add_months(payment_date, 1)
		payment_date_obj = payment_date

		if isinstance(payment_date, basestring):
			payment_date_obj = datetime.strptime(payment_date, frappe.utils.DATE_FORMAT)

		payment_date_str = payment_date_obj.strftime(frappe.utils.DATE_FORMAT)

		if capital_balance < 0.000 or interest_balance < 0.000:
		 	capital_balance = interest_balance = 0.000

		 	if len(self.repayment_schedule) >= int(self.repayment_periods):
		 		self.repayment_periods += 1
		
		self.append("repayment_schedule", {
			"fecha": payment_date_str,
			"cuota": cuota,
			"monto_pendiente": cuota,
			"show_capital": round(self.monthly_capital),
			"capital": round(self.monthly_capital),
			"interes": cuota - round(self.monthly_capital),
			"show_interes": cuota - round(self.monthly_capital),
			"balance_capital": round(capital_balance),
			"balance_interes": round(interest_balance),
			"capital_acumulado": round(capital_acumulado),
			"interes_acumulado": round(interes_acumulado),
			"pagos_acumulados": pagos_acumulados,
			"fecha_mes": from_en_to_es("{0:%B}".format(payment_date_obj)),
			"estado": PENDING
		})

	# round the amounts
	self.monthly_repayment_amount = round(self.monthly_repayment_amount)
	self.total_payment = round(self.total_payable_amount)
	self.total_payable_amount = round(self.total_payable_amount)
	self.total_interest_payable = round(self.total_payable_interest)
	self.total_payable_interest = round(self.total_payable_interest)

@frappe.whitelist()
def loan_disbursed_amount(loan):
	return frappe.db.sql("""SELECT IFNULL(SUM(debit_in_account_currency), 0.000) AS disbursed_amount 
		FROM `tabGL Entry` 
		WHERE against_voucher_type = 'Loan' 
		AND against_voucher = %s""", 
		(loan), as_dict=1)[0]

@frappe.whitelist()
def make_payment_entry(doctype, docname, paid_amount, capital_amount, interest_amount, posting_date=0.000, fine=0.000, fine_discount=0.000, other_discounts=0.000, insurance=0.000, gps=0.000, recuperacion=0.000, create_jv=True):
	from erpnext.accounts.utils import get_account_currency
	from fm.api import get_voucher_type

	if not posting_date:
		posting_date = frappe.utils.nowdate()

	# load the loan from the database to make the requests more
	# efficients as the browser won't have to send everything back
	loan = frappe.get_doc(doctype, docname)

	curex = frappe.get_value("Currency Exchange", 
		{"from_currency": "USD", "to_currency": "DOP"}, "exchange_rate")

	exchange_rate = curex if loan.customer_currency == "USD" else 0.000

	# validate if the user has permissions to do this
	frappe.has_permission('Journal Entry', throw=True)

	def make(journal_entry, _paid_amount, _capital_amount=0.000, _interest_amount=0.000,  _insurance=0.000, _fine=0.000, _fine_discount=0.000, _gps=0.000, _recuperacion=0.000):
		party_type = "Customer"
		voucher_type = get_voucher_type(loan.mode_of_payment)
		party_account_currency = get_account_currency(loan.customer_loan_account)
		today = frappe.utils.nowdate()

		interest_for_late_payment = frappe.db.get_single_value("FM Configuration", "interest_for_late_payment")
		account_of_suppliers = frappe.db.get_single_value("FM Configuration", "account_of_suppliers")
		interest_on_loans = frappe.db.get_single_value("FM Configuration", "interest_on_loans")
		goods_received_but_not_billed = frappe.db.get_single_value("FM Configuration", "goods_received_but_not_billed")
		interest_income_account = frappe.db.get_single_value("FM Configuration", "interest_income_account")
		default_discount_account = frappe.db.get_single_value("FM Configuration", "default_discount_account")

		if loan.customer_currency == "USD":
			default_discount_account = default_discount_account.replace("DOP","USD")

		filters = { 
			"loan": loan.name,
			"docstatus": "1",
			"start_date": ["<=", today],
			"end_date": [">=", today] 
		}
		 
		insurance_supplier = frappe.get_value("Poliza de Seguro", filters, "insurance_company")

		if not insurance_supplier:
			# insurance supplier was not found in the Poliza de Seguro document. setting default
			insurance_supplier = frappe.db.get_single_value("FM Configuration", "default_insurance_supplier")

		# journal_entry = frappe.new_doc('Journal Entry')
		journal_entry.voucher_type = voucher_type
		journal_entry.user_remark = _('Pagare de Prestamo: %(name)s' % { 'name': loan.name })
		journal_entry.company = loan.company
		journal_entry.posting_date = posting_date

		journal_entry.es_un_pagare = 1
		journal_entry.loan = loan.name

		journal_entry.append("accounts", {
			"account": loan.payment_account,
			"debit_in_account_currency": _paid_amount,
			"reference_type": loan.doctype,
			"reference_name": loan.name,
			"exchange_rate": exchange_rate,
			"repayment_field": "paid_amount"
		})
		if flt( _gps or _recuperacion ):
			_gps = flt(_gps)
			_recuperacion = flt(_recuperacion)

			journal_entry.append("accounts", {
				"account": interest_for_late_payment,
				"debit_in_account_currency": _recuperacion + _gps,
				"account_currency": "DOP",
				"reference_type": loan.doctype,
                "reference_name": loan.name
			})

		if flt(_fine_discount):
			journal_entry.append("accounts", {
				"account": default_discount_account,
				"debit_in_account_currency": _fine_discount,
				"exchange_rate": exchange_rate,
				"repayment_field": "fine_discount"
			})

		# if flt(other_discounts):
		# 	journal_entry.append("accounts", {
		# 		"account": default_discount_account,
		# 		"debit_in_account_currency": other_discounts,
		# 		"exchange_rate": exchange_rate,
		# 		"repayment_field": "fine_discount"
		# 	})

		if flt(_capital_amount):
			journal_entry.append("accounts", {
				"account": loan.customer_loan_account,
				"party_type": "Customer",
				"party": loan.customer,
				"credit_in_account_currency": _capital_amount,
				"exchange_rate": exchange_rate,
				"repayment_field": "capital"
			})	

		if flt(_interest_amount):
			journal_entry.append("accounts", {
				"account": loan.customer_loan_account,
				"party_type": "Customer",
				"party": loan.customer,
				"credit_in_account_currency": _interest_amount,
				"exchange_rate": exchange_rate,
				"repayment_field": "interes"
			})

		if flt(_insurance):
			journal_entry.append("accounts", {
				"account": loan.customer_loan_account,
				"party_type": "Customer",
				"party": loan.customer,
				"credit_in_account_currency": _insurance,
				"exchange_rate": exchange_rate,
				"repayment_field": "insurance"
			})

		if flt(_gps):
			journal_entry.append("accounts", {
				"account": goods_received_but_not_billed,
				"reference_type": loan.doctype,
                "reference_name": loan.name,
				"credit_in_account_currency": _gps,
				"repayment_field": "gps"
			})

		if flt(_recuperacion):
			journal_entry.append("accounts", {
				"account": goods_received_but_not_billed,
				"reference_type": loan.doctype,
                "reference_name": loan.name,
				"credit_in_account_currency": _recuperacion,
				"repayment_field": "gastos_recuperacion"
			})	

		if flt(_fine):
			journal_entry.append("accounts", {
				"account": fm.api.get_currency(loan, interest_on_loans),
				"credit_in_account_currency": _fine,
				"exchange_rate": exchange_rate,
				"repayment_field": "fine"
			})

		journal_entry.multi_currency = 1.000 if loan.customer_currency == "USD" else 0.000

		journal_entry.submit()
		return journal_entry

	_paid_amount = flt(paid_amount) + flt(other_discounts)
 	rate = exchange_rate if loan.customer_currency == "USD" else 1.000

	while _paid_amount > 0.000:
		# to create the journal entry we will need some temp files
		# these tmp values will store the actual values for each row before they are changed
		tmp_fine = tmp_capital = tmp_interest = tmp_insurance = 0.000

		# to know how much exactly was paid for this repayment
		temp_paid_amount = _paid_amount

		# get the repayment from the loan
		row = loan.next_repayment()

		if not row:
			frappe.throw("""<h4>Parece que este prestamo no tiene mas pagares.</h4>
				<b>Si esta pagando multiples cuotas, es probable que el monto que este digitando
				sea mayor al monto total pendiente del prestamo!</b>""")

		# duty without the fine discount applied which is the original duty
		duty = flt(row.capital) + flt(row.interes) + flt(row.fine) + flt(row.insurance)

		# let's validate that the user is not applying discounts for multiple payments
		if flt(fine_discount) and not row.fine:
			frappe.throw("No puede hacerle descuento a la mora si el cliente no tiene Mora!")
		if flt(fine_discount) > row.fine:
			frappe.throw("No es posible hacer descuentos mayores a la Mora!")
		if flt(fine_discount) and _paid_amount > duty:
			frappe.throw("No esta permitido hacer descuento de mora para pagos de multiples cuotas!")
		
		# duty with the fine discount applied
		# at this point we are sure that if there is any discount it is only applicable for one repayment
		duty = flt(row.capital) + flt(row.interes) + flt(row.fine) + flt(row.insurance) - flt(fine_discount)
		
		if _paid_amount >= row.fine: 
			tmp_fine = row.fine
			_paid_amount -= row.fine
			row.fine = 0.000
		else:
			tmp_fine = _paid_amount
			row.fine -= _paid_amount
	 		_paid_amount = 0.000

		if _paid_amount >= row.interes: 
			tmp_interest = row.interes
	 		_paid_amount -= row.interes
			row.interes = 0.000
		else:
			tmp_interest = _paid_amount
			row.interes -= _paid_amount
	 		_paid_amount = 0.000


		if _paid_amount >= row.capital: 
			tmp_capital = row.capital
	 		_paid_amount -= row.capital
			row.capital = 0.000
		else:
			tmp_capital = _paid_amount
			row.capital -= _paid_amount
	 		_paid_amount = 0.000


		if _paid_amount >= row.insurance:
			tmp_insurance = row.insurance
	 		_paid_amount -= row.insurance
			row.insurance = 0.000

			# Cambiar el estado de la cuota de la poliza de seguro a SALDADA 
	 		fm.api.update_insurance_status("SALDADO", row.insurance_doc)
		else:
			tmp_insurance = _paid_amount
			row.insurance -= _paid_amount
	 		_paid_amount = 0.000

			# Cambiar el estado de la cuota de la poliza de seguro a ABONO 
	 		fm.api.update_insurance_status("ABONO", row.insurance_doc)
		
		repayment_amount = tmp_fine + tmp_interest + tmp_capital + tmp_insurance - flt(fine_discount)
		
		if repayment_amount >= duty:

			row.monto_pendiente = 0.000
		else:
			row.monto_pendiente = flt(duty) - flt(repayment_amount)
			# row.monto_pendiente = flt(row.capital) + flt(row.interes) + flt(row.fine) + flt(row.insurance)

		row.update_status()
		if create_jv:
			
			payment_entry = frappe.new_doc("Journal Entry")

			payment_entry.pagare = row.name
			payment_entry.loan = loan.name

			payment_entry.insurance_amount = tmp_insurance
			payment_entry.dutty_amount = row.cuota
			payment_entry.partially_paid = temp_paid_amount - duty if temp_paid_amount > duty else temp_paid_amount
			payment_entry.amount_paid = fm.api.get_paid_amount_for_loan(loan.customer, loan.posting_date)
			payment_entry.fine_discount = fine_discount
			payment_entry.gps = gps
			payment_entry.gastos_recuperacion = recuperacion
			payment_entry.loan_amount = loan.total_payment
			payment_entry.insurance_amount = tmp_insurance
			payment_entry.pending_amount = fm.api.get_pending_amount_for_loan(loan.customer, loan.posting_date)
			payment_entry.mode_of_payment = loan.mode_of_payment
			payment_entry.fine = tmp_fine
			payment_entry.repayment_no = row.idx
			payment_entry.currency = loan.customer_currency
			payment_entry.due_date = row.fecha

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=repayment_amount if temp_paid_amount > duty else temp_paid_amount,
				_capital_amount=tmp_capital, 
				_interest_amount=tmp_interest, 
				_insurance=tmp_insurance, 
				_fine=tmp_fine, 
				_fine_discount=fine_discount,
				_gps=gps, 
				_recuperacion=recuperacion
			)

		row.db_update()
		loan.update_disbursement_status()

		loan.db_update()

@frappe.whitelist()
def cashier_control(frm, data):
	import json
	# validate if the user has permissions to do this
	frappe.has_permission('Journal Entry', throw=True)

	# I received frm and data as string, let's decode and make it a dict 
	data = frappe._dict(json.loads(data))
	frm = frappe._dict(json.loads(frm))
	
	dop = flt(data.get("amount_dop")) if flt(data.get("amount_dop")) else 0.000    
	usd = flt(data.get("amount_usd")) if flt(data.get("amount_usd")) else 0.000    

	journal_entry = frappe.new_doc("Journal Entry")
	journal_entry.voucher_type = "Journal Entry"
	journal_entry.user_remark = _("{}".format(data.get("type")))
	journal_entry.company = data.get("company")
	journal_entry.posting_date = frappe.utils.nowdate()
	journal_entry.multi_currency = 1.000 if usd  else 0.000
	journal_entry.is_cashier_closing = 1

	if dop:
		debit_account = frm.cashier_account if data.get("type") == "OPEN" else frm.bank_account
		credit_account = frm.bank_account if data.get("type") == "OPEN" else frm.cashier_account

		journal_entry.append("accounts", {
			"account": debit_account,
			"debit_in_account_currency": dop,
		})
		journal_entry.append("accounts", {
			"account": credit_account,
			"credit_in_account_currency": dop,
		})

	if usd:
		debit_account_usd = frm.cashier_account_usd if data.get("type") == "OPEN" else frm.bank_account_usd
		credit_account_usd = frm.bank_account_usd if data.get("type") == "OPEN" else frm.cashier_account_usd

		journal_entry.append("accounts", {
			"account": debit_account_usd,
			"debit_in_account_currency": usd,
		})
		journal_entry.append("accounts", {
			"account": credit_account_usd,
			"credit_in_account_currency": usd,
		})
	
	journal_entry.submit()
	
	frm.entries.insert(0, {
		"idx": 0,
		"date": frappe.utils.nowdate(),
		"user": frappe.session.user,
		"type": data.get("type"),
		"amount": dop,
		"amount_usd": usd,
		"reference": journal_entry.name
	})

	entries = []
	for idx, current in enumerate(frm.entries):
		current = frappe._dict(current)
		current.idx = idx + 1

		entries.append(current)

	frm.entries = entries
	return frm

