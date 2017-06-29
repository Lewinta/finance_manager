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
	if doc.loan:
		loan = frappe.get_doc("Loan", doc.loan)

		loan.update_disbursement_status()
		
		update_repayment_amount(doc)
		
		loan.db_update()
		
def cancel_journal(doc, event):
	if doc.loan:
		# fetch it from the DB first
		loan = frappe.get_doc("Loan", doc.loan)

		update_repayment_amount(doc)
		
		if not doc.es_un_pagare:
			if frappe.get_list("Journal Entry", {"loan": loan.name, "es_un_pagare": "1"}):
				frappe.throw("No puede cancelar este desembolso con pagares hechos!")
				
		loan.update_disbursement_status(doc.name)

		loan.db_update()
	
def update_repayment_amount(doc):
	if doc.es_un_pagare:
		# update repayment

		try:

			paid_amount = 0

			# load the repayment to work it
			row = frappe.get_doc("Tabla Amortizacion", doc.pagare)
			
			filters = { 
				"pagare": row.name,
				"name": ["!=", doc.name] 
			}

			# let's see how much the customer has paid so far for this repayment
			for journal in frappe.get_list("Journal Entry", filters, "total_amount"):
				paid_amount += journal.total_amount

			# duty will be what the customer has to pay for this repayment
			duty = flt(row.cuota) + flt(row.fine) + flt(row.insurance)

			# then, the outstanding amount will be the 
			# duty less what he's paid so far
			row.monto_pendiente = duty - paid_amount

			# update the status of the repayment
			row.update_status()

			# save to the database
			row.db_update()
		except:
			frappe.msgprint("There was an error!")

def get_repayment_details(loantype):

	# validate that the interest type is simple
	if loantype.interest_type == "Simple":
		return get_simple_repayment_details(loantype)

	elif loantype.interest_type == "Composite":
		return get_compound_repayment_details(loantype)		

def get_simple_repayment_details(loantype):
	# if there's not rate set
	if not loantype.rate_of_interest: 	
		# now let's fetch from the DB the default rate for interest simple
		loantype.rate_of_interest = frappe.db.get_single_value("FM Configuration", "simple_rate_of_interest")

	# convert the rate of interest to decimal
	loantype.rate = flt(loantype.rate_of_interest) / 100.0

	# calculate the monthly interest
	loantype.monthly_interest = round(loantype.loan_amount * loantype.rate)

	# ok, now let's check the repayment method
	if loantype.repayment_method == "Repay Over Number of Periods":

		# total interest
		loantype.total_payable_interest = loantype.monthly_interest * loantype.repayment_periods

		# calculate the monthly capital
		loantype.monthly_capital = flt(loantype.loan_amount) / flt(loantype.repayment_periods)

	elif loantype.repayment_method == "Repay Fixed Amount per Period":
		
		# calculate the monthly capital
		loantype.monthly_capital = flt(loantype.monthly_repayment_amount) - loantype.monthly_interest

		if loantype.monthly_capital < 0:
			frappe.throw(_("Monthly repayment amount cannot be less than the monthly interest!"))

		# calculate the repayment periods based on the given monthly repayment amount
		loantype.repayment_periods = flt(loantype.loan_amount) / flt(loantype.monthly_capital)

		# total interest
		loantype.total_payable_interest = loantype.monthly_interest * loantype.repayment_periods

	# get the monthly repayment amount
	loantype.monthly_repayment_amount = round(loantype.monthly_interest + loantype.monthly_capital)

	# calculate the total payment
	loantype.total_payable_amount = loantype.monthly_repayment_amount * loantype.repayment_periods

def get_compound_repayment_details(loantype):
	# if there's not rate set
	if not loantype.rate_of_interest: 
		# now let's fetch from the DB the default rate for interest compound
		loantype.rate_of_interest = frappe.db.get_single_value("FM Configuration", "composite_rate_of_interest")
	
	if loantype.repayment_method == "Repay Over Number of Periods":
		loantype.repayment_amount = \
			get_monthly_repayment_amount(
				loantype.interest_type,
				loantype.repayment_method, 
				loantype.loan_amount, 
				loantype.rate_of_interest, 
				loantype.repayment_periods
			)

	if loantype.repayment_method == "Repay Fixed Amount per Period":

		# convert the rate to decimal
		monthly_interest_rate = flt(loantype.rate_of_interest) / 100.0

		if monthly_interest_rate:
			loantype.repayment_periods = round(
				flt(
					log(loantype.repayment_amount) 
					- log(loantype.repayment_amount 
						- flt(loantype.loan_amount 
							* monthly_interest_rate ))) 
				/ flt(log(monthly_interest_rate	+1 ))
			)
		else:
			loantype.repayment_periods = loantype.loan_amount / loantype.repayment_amount

	loantype.calculate_payable_amount()

def make_simple_repayment_schedule(loantype):
	from fm.api import from_en_to_es
	
	# let's get the loan details
	get_repayment_details(loantype)
	
	# let's clear the table
	loantype.repayment_schedule = []

	# set defaults for this variables
	capital_balance = loantype.loan_amount
	interest_balance = loantype.total_payable_interest
	## loantype.repayment_periods = ceil(loantype.repayment_periods)
	pagos_acumulados = interes_acumulado = 0
	capital_acumulado = 0

	
	payment_date = loantype.get("disbursement_date") if loantype.get("disbursement_date") else loantype.get("posting_date")

	# map the values from the old variables
	loantype.total_payment = loantype.total_payable_amount
	loantype.total_interest_payable = loantype.total_payable_interest

	# fetch from the db the maximun pending amount for a loan
	maximum_pending_amount = frappe.db.get_single_value("FM Configuration", "maximum_pending_amount")

	# ok, now let's add the records to the table
	while(capital_balance > flt(maximum_pending_amount)):

		monthly_repayment_amount = loantype.monthly_repayment_amount

		# if(capital_balance + interest_balance < monthly_repayment_amount ):
		cuota =  round(loantype.monthly_capital) + loantype.monthly_interest
			
		capital_balance -= loantype.monthly_capital
		interest_balance -= loantype.monthly_interest
		pagos_acumulados += monthly_repayment_amount
		interes_acumulado += loantype.monthly_interest
		capital_acumulado += loantype.monthly_capital

		# start running the dates
		payment_date = frappe.utils.add_months(payment_date, 1)
		payment_date_obj = payment_date

		if isinstance(payment_date, basestring):
			payment_date_obj = datetime.strptime(payment_date, frappe.utils.DATE_FORMAT)

		payment_date_str = payment_date_obj.strftime(frappe.utils.DATE_FORMAT)

		if capital_balance < 0 or interest_balance < 0:
		 	capital_balance = interest_balance = 0

		 	if len(loantype.repayment_schedule) >= int(loantype.repayment_periods):
		 		loantype.repayment_periods += 1
		
		loantype.append("repayment_schedule", {
			"fecha": payment_date_str,
			"cuota": cuota,
			"monto_pendiente": cuota,
			"capital": round(loantype.monthly_capital),
			"interes": loantype.monthly_interest,
			"balance_capital": round(capital_balance),
			"balance_interes": round(interest_balance),
			"capital_acumulado": round(capital_acumulado),
			"interes_acumulado": round(interes_acumulado),
			"pagos_acumulados": pagos_acumulados,
			"fecha_mes": from_en_to_es("{0:%B}".format(payment_date_obj)),
			"estado": PENDING
		})

@frappe.whitelist()
def loan_disbursed_amount(loan):
	return frappe.db.sql("""SELECT IFNULL(SUM(debit_in_account_currency), 0) AS disbursed_amount 
		FROM `tabGL Entry` 
		WHERE against_voucher_type = 'Loan' 
		AND against_voucher = %s""", 
		(loan), as_dict=1)[0]

@frappe.whitelist()
def make_payment_entry(doctype, docname, paid_amount, capital_amount, interest_amount, fine=0, fine_discount=0, insurance=0):
	from erpnext.accounts.utils import get_account_currency
	from fm.api import get_voucher_type

	# validate if the user has permissions to do this
	frappe.has_permission('Journal Entry', throw=True)

	def make(journal_entry, _paid_amount, _capital_amount=0, _interest_amount=0,  _insurance=0, _fine=0, _fine_discount=0):
		party_type = "Customer"

		voucher_type = get_voucher_type(loan.mode_of_payment)
		party_account_currency = get_account_currency(loan.customer_loan_account)
		today = frappe.utils.nowdate()

		interest_for_late_payment = frappe.db.get_single_value("FM Configuration", "interest_for_late_payment")
		account_of_suppliers = frappe.db.get_single_value("FM Configuration", "account_of_suppliers")
		interest_on_loans = frappe.db.get_single_value("FM Configuration", "interest_on_loans")

		filters = { 
			"loan": loan.name,
			"docstatus": "1",
			"start_date": ["<=", today],
			"end_date": [">=", today] 
		}
		
		insurance_supplier = frappe.get_value("Poliza de Seguro", filters, "insurance_company")

		# journal_entry = frappe.new_doc('Journal Entry')
		journal_entry.voucher_type = voucher_type
		journal_entry.user_remark = _('Pagare de Prestamo: %(name)s' % { 'name': loan.name })
		journal_entry.company = loan.company
		journal_entry.posting_date = today

		journal_entry.es_un_pagare = 1
		journal_entry.loan = loan.name

		journal_entry.append("accounts", {
			"account": loan.payment_account,
			"debit_in_account_currency": _paid_amount,
			"reference_type": loan.doctype,
			"reference_name": loan.name
		})

		if _fine_discount:
			journal_entry.append("accounts", {
				"account": interest_for_late_payment,
				"debit_in_account_currency": _fine_discount,
			})

		if _capital_amount:
			journal_entry.append("accounts", {
				"account": loan.customer_loan_account,
				"party_type": "Customer",
				"party": loan.customer,
				"credit_in_account_currency": _capital_amount,
			})	

		if _interest_amount:
			journal_entry.append("accounts", {
				"account": loan.interest_income_account,
				"credit_in_account_currency": _interest_amount,
			})

		if _insurance:
			journal_entry.append("accounts", {
				"account": account_of_suppliers,
				"credit_in_account_currency": _insurance,
				"party_type": "Supplier",
				"party": insurance_supplier,
			})

		if _fine:
			journal_entry.append("accounts", {
				"account": interest_on_loans,
				"credit_in_account_currency": _fine,
			})

		journal_entry.submit()

		return journal_entry

	# load the loan from the database to make the requests more
	# efficients as the browser won't have to send everything back
	loan = frappe.get_doc(doctype, docname)

	_paid_amount = flt(paid_amount)

	while _paid_amount > 0:
		prev_amount = 0
		row = loan.next_repayment()

		for journal in frappe.get_list("Journal Entry", { "pagare": row.name }, "total_amount"):
			prev_amount += journal.total_amount

		# duty will be what the customer has to pay for this pagare
		duty = flt(row.cuota) + flt(row.fine) + flt(row.insurance)

		row.monto_pendiente = 0 if _paid_amount > duty else duty - _paid_amount - prev_amount

		payment_entry = frappe.new_doc("Journal Entry")

		payment_entry.pagare = row.name
		payment_entry.loan = loan.name

		row.update_status()

		if _paid_amount == row.capital:

			already_paid = fm.api.get_paid_amount(loan.customer_loan_account, row.name)
			new_capital_amount = row.capital - already_paid
			if already_paid:
				payment_entry = make(journal_entry=payment_entry,
					_paid_amount=_paid_amount,
					_capital_amount=row.capital - already_paid,
					_interest_amount=already_paid + _interest_amount - row.capital
				)

			else:
				payment_entry = make(journal_entry=payment_entry,
					_paid_amount=_paid_amount,
					_capital_amount=row.capital,
				)
		elif _paid_amount == (row.capital + row.interes):

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=row.interes
			)
		elif _paid_amount == (row.capital + row.interes + row.insurance):

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=row.interes, 
				_insurance=row.insurance
			)
		elif _paid_amount == (row.capital + row.interes + row.insurance + row.fine) and not fine_discount:

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=row.interes, 
				_insurance=row.insurance, 
				_fine=row.fine
			)
		elif _paid_amount == (row.capital + row.interes + row.insurance + row.fine) and fine_discount:

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=row.interes, 
				_insurance=row.insurance, 
				_fine=row.fine, 
				_fine_discount=fine_discount)
		elif _paid_amount < row.capital:

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=_paid_amount
			)
		elif _paid_amount < (row.capital + row.interes):

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=_paid_amount - row.capital
			)
		elif _paid_amount < (row.capital + row.interes + row.insurance):

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=_paid_amount,
				_capital_amount=row.capital, 
				_interest_amount=row.interes, 
				_insurance=_paid_amount - row.capital - row.interes
			)
		elif _paid_amount > duty:


			if flt(fine_discount):
				frappe.throw("No esta permitido hacer descuento de mora para pagos de multiples cuotas!")

			payment_entry = make(journal_entry=payment_entry,
				_paid_amount=duty, 
				_capital_amount=row.capital,
				_interest_amount=row.interes,
				_insurance=row.insurance, 
				_fine=row.fine
			)
				
		_paid_amount -= duty

		row.db_update()
