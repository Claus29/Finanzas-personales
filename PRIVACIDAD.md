# Política de privacidad — Bot Finanzas Personales

_Última actualización: 23 de octubre de 2026_

## Quién es el responsable

Este es un proyecto personal y sin ánimo de lucro de Claus29 (titular del repositorio
[Claus29/Finanzas-personales](https://github.com/Claus29/Finanzas-personales)).
El bot está pensado para el **uso exclusivo de su titular**, que es quien conecta sus
propias cuentas bancarias.

## Qué datos se tratan

A través de Enable Banking (proveedor de servicios de información de cuentas, AIS, bajo PSD2)
el bot puede **leer**:

- Datos de las cuentas: IBAN, titular, nombre de la cuenta.
- Saldos.
- Movimientos: fecha, importe, moneda, concepto y contraparte.

El bot **no inicia pagos** ni puede mover dinero. Tampoco recibe ni guarda las credenciales
de acceso al banco: la autorización se hace directamente en la app o web del banco.

## Para qué se usan

Solo para que el titular lleve su contabilidad personal: registrar gastos e ingresos,
categorizarlos y generar resúmenes, presupuestos, alertas y estadísticas.

## Dónde se guardan y durante cuánto tiempo

- En la base de datos del propio bot, en un servidor controlado por el titular.
- Las claves de acceso se guardan cifradas o en variables de entorno, nunca en el código.
- Los datos se conservan mientras el titular use el bot y se pueden borrar en cualquier momento.

## Con quién se comparten

Con nadie. Los datos no se venden, no se ceden a terceros y no se usan con fines publicitarios.
Los únicos servicios que intervienen son Enable Banking (para leer los datos del banco) y
Telegram (para mostrar la información en el chat).

## Cómo retirar el permiso

- Revocando el acceso desde la app del banco (apartado de apps o proveedores conectados) o
  desde Enable Banking.
- El permiso caduca solo al terminar su periodo de validez (normalmente 90–180 días).
- Al revocarlo, el bot deja de recibir datos nuevos.

## Contacto

Para cualquier consulta sobre privacidad, abre un _issue_ en
[el repositorio](https://github.com/Claus29/Finanzas-personales/issues) o usa el email
de protección de datos indicado en el registro de la aplicación en Enable Banking.
