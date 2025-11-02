import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import './styles/global.css'
import Home from './pages/Home'
import BuildProgress from './pages/BuildProgress'
import Result from './pages/Result'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />}> 
        <Route index element={<Home />} />
        <Route path="progress/:buildId" element={<BuildProgress />} />
        <Route path="result/:buildId" element={<Result />} />
      </Route>
    </Routes>
  </BrowserRouter>
)
