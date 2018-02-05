# -*- encoding: utf-8 -*-

import frappe
from datetime import date
from frappe.utils import flt

from fm.api import PENDING

@frappe.whitelist()
def get_next_repayment_schedule(chasis_no):
	loan_id = frappe.get_value("Loan", { "asset": chasis_no }, "name")

	if not loan_id:
		next_month = frappe.utils.add_months(date.today(), 1)

		return next_month.strftime("%Y-%m-%d")

	loan = frappe.get_doc("Loan", loan_id)

	pagos_vencidos = [ row for row in loan.repayment_schedule if row.estado == PENDING ]

	pagare = pagos_vencidos[0]

	fecha_pagare = pagare.fecha

	return fecha_pagare.strftime('%Y-%m-%d')
	
@frappe.whitelist()
def add_insurance_to_loan(chasis_no, total_insurance):
	doc = frappe.get_doc("Loan", { "asset": chasis_no, "status": "Fully Disbursed" })
	doc.vehicle_insurance = total_insurance

	doc.save()

	return doc.name

def s_sanitize(string):
	"""Remove the most common special caracters"""

	special_cars = [
		(u"á", "a"), (u"Á", "A"),
		(u"é", "e"), (u"É", "E"),
		(u"í", "i"), (u"Í", "I"),
		(u"ó", "o"), (u"Ó", "O"),
		(u"ú", "u"), (u"Ú", "U"),
		(u"ü", "u"), (u"Ü", "U"),
		(u"ñ", "n"), (u"Ñ", "N")
	]

	s_sanitized = string

	for pair in special_cars:
		s_sanitized = s_sanitized.replace(pair[0], pair[1])

	return s_sanitized.upper()

@frappe.whitelist()
def clean_all_fines(loan):
	_log = 'done'
	doc = frappe.get_doc('Loan',loan)
	for r in frappe.get_list('Tabla Amortizacion', {'parent':loan}, 'name'):
		row = frappe.get_doc('Tabla Amortizacion', r.name)
		if not row.estado == "SALDADA":
			row.monto_pendiente = row.monto_pendiente - row.fine
			row.fine = 0
			row.db_update()

	#Let's leave some trace
	doc.add_comment("Updated", "<span>Eliminó todas las moras de este prestamo.</span>", frappe.session.user)			
	return _log

@frappe.whitelist()
def add_fine(loan,cuota,mora):
	doc = frappe.get_doc('Loan',loan)
	mora = flt(mora)
	row = frappe.get_doc('Tabla Amortizacion', {'parent': loan, 'idx': cuota})
	row.fine += mora
	row.monto_pendiente = row.monto_pendiente + mora
	row.db_update()

	#Let's leave some trace
	doc.add_comment("Updated", "<span>Agregó  ${} de mora a la cuota No. {}.</span>".format(mora, cuota), frappe.session.user)			

