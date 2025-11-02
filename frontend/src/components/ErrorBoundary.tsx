import React from 'react'

type State = { hasError: boolean, error?: any }

export default class ErrorBoundary extends React.Component<React.PropsWithChildren<{}>, State> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError(error: any) { return { hasError: true, error } }
  componentDidCatch(error: any, info: any) { console.error('UI error:', error, info) }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 text-sm">
          <div className="text-red-400 mb-2">Something went wrong.</div>
          <button className="bg-gray-800 border border-gray-700 rounded px-3 py-2" onClick={()=>location.reload()}>Reload</button>
        </div>
      )
    }
    return this.props.children as any
  }
}