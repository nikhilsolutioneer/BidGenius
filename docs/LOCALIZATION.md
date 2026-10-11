# English and German interface

The top-right language selector supports English (`en`, default) and German (`de`). `bidgenius_language` in browser local storage persists the choice. Selection also updates the HTML `lang` attribute and synchronizes across tabs without reloading or resetting application state.

The implementation translates known interface messages locally. It does not send document or customer text to an external translation service. Original tender text, input values, IDs, enum values, filenames, and financial calculations remain unchanged. `api.ts` uses locale-aware dates and Swiss number symbols while retaining exact decimal-string rounding.

## Adding interface text

`frontend/src/i18n/de.json` maps English interface messages to their German translations. Dynamic messages can use numbered placeholders, for example `{0} positions`. Add complete messages rather than translating arbitrary words in source documents. English remains the fallback for unrecognized text. A candidate inventory can be generated from the frontend directory with `node scripts/list-ui-messages.mjs`.

The app's automatic JSX runtime (`src/i18n/jsx-runtime.ts` and `jsx-dev-runtime.ts`) translates text children and accessible text attributes of native elements during React rendering. It never mutates the DOM behind React or changes component business props. Implicit option values are captured before their labels are translated. Mark original evidence or brand strings `translate="no"`; preformatted/code content is preserved by default. Third-party components that render their own native text, such as Radix dialog titles, use `translate()` explicitly.

`App` subscribes to the language store so switching re-renders its existing tree without a key change or remount. The Vite configuration excludes the application JSX runtime from dependency prebundling to ensure it shares the same live language store. Preserve this exclusion when modifying the build setup.

## Verification

`frontend/tests/language.spec.ts` uses mocked API routes and covers switching both ways, translated dialog/accessibility labels, persistence, mobile layout, unchanged prices, preserved input state and role values, original source protection, and implicit option values. It never mutates saved projects. The existing hybrid workflow and decimal-format tests cover interaction with processing controls and money formatting.
